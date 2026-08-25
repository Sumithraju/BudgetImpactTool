"""Adverse-event economics — M13, the impure half.

Resolves stored incidences and unit costs into the `SafetyProfile` the engine
consumes, and decides what the *absence* of a profile means. The arithmetic
itself lives in `biet_engine.safety` and knows nothing about any of this.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from sqlalchemy.orm import Session

from biet_engine.models import (
    AdverseEvent as EngineEvent,
)
from biet_engine.models import (
    ConfidenceTier,
    EventIncidence,
    Money,
    Provenance,
    ResolutionLevel,
    SafetyProfile,
    Valued,
    Warning_,
)
from biet_engine.safety import annualise, expected_ae_cost

from ..constants.domain import WarningCode
from ..repositories.safety import SafetyRepository

log = logging.getLogger("biet.safety")


class SafetyService:
    """Expected adverse-event cost per therapy per market."""

    def __init__(self, session: Session) -> None:
        self._repo = SafetyRepository(session)

    def resolve_ae_costs(
        self, drug_ids: Sequence[int], country_codes: Sequence[str],
        currencies: Mapping[str, str],
    ) -> tuple[dict[tuple[int, str], Money], tuple[Warning_, ...]]:
        """`(drug_id, country_code) -> expected annual AE cost`, plus warnings.

        A therapy with no stored profile is absent from the mapping rather
        than present with a zero: zero is a claim that the therapy causes no
        manageable events, and "we have no profile" is not that claim. The
        caller distinguishes them; this function does not paper over the
        difference.
        """
        incidences = self._repo.load_incidences(drug_ids)
        unit_costs = self._repo.load_unit_costs(country_codes)

        costs: dict[tuple[int, str], Money] = {}
        warnings: list[Warning_] = []
        derived_markets: set[str] = set()

        for code in country_codes:
            currency = currencies[code]
            for drug_id in drug_ids:
                rows = incidences.get(drug_id)
                if not rows:
                    continue

                events: list[EventIncidence] = []
                for row in rows:
                    unit = unit_costs.get((row.ae_code, code))
                    if unit is None:
                        # An incidence with no cost in this market prices at
                        # nothing. Skipped rather than defaulted, and the
                        # market-level warning below says the profile is
                        # incomplete.
                        derived_markets.add(code)
                        continue
                    if ConfidenceTier(unit.confidence_tier) in _DERIVED_TIERS:
                        derived_markets.add(code)

                    events.append(EventIncidence(
                        event=EngineEvent(
                            code=row.ae_code,
                            label=row.ae_code.replace("_", " ").title(),
                            is_serious=False,
                        ),
                        incidence=Valued(
                            value=float(row.incidence),
                            provenance=Provenance(
                                source=row.source,
                                vintage_year=row.vintage_year,
                                confidence_tier=ConfidenceTier(row.confidence_tier),
                                resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
                                note=row.population,
                            ),
                        ),
                        exposure_weeks=row.exposure_weeks,
                        unit_cost=Money(
                            amount=float(unit.unit_cost_local), currency=currency,
                        ),
                    ))

                if not events:
                    continue

                profile = SafetyProfile(
                    drug_id=drug_id, country_code=code, events=tuple(events),
                )
                costs[(drug_id, code)] = expected_ae_cost(profile, currency)

        warnings.extend(self._asymmetry_warnings(drug_ids, country_codes, costs))
        for code in sorted(derived_markets):
            warnings.append(Warning_(
                code=WarningCode.AE_COST_DERIVED,
                message=(
                    "Adverse-event management costs for this market are analyst "
                    "constructions rather than observed costs, or are missing for "
                    "some events. The same class of caveat as a purchasing-power-"
                    "derived price."
                ),
                country_code=code,
            ))
        return costs, tuple(warnings)

    def comparison(self, drug_ids: Sequence[int], country_code: str) -> dict[str, object]:
        """Every priced event for a set of therapies, side by side.

        The economic figure is one number per therapy; this is what it was
        computed from. Each incidence carries the trial it came from and the
        population it was observed in, because an adverse-event rate with no
        stated population is not a fact about anyone in particular.
        """
        incidences = self._repo.load_incidences(drug_ids)
        unit_costs = self._repo.load_unit_costs([country_code])

        rows: list[dict[str, object]] = []
        for event in self._repo.list_events():
            unit = unit_costs.get((event.ae_code, country_code))
            per_drug: dict[str, object] = {}
            for drug_id in drug_ids:
                row = next(
                    (r for r in incidences.get(drug_id, []) if r.ae_code == event.ae_code),
                    None,
                )
                if row is None:
                    continue
                observed = float(row.incidence)
                per_drug[str(drug_id)] = {
                    "observed": observed,
                    "annualised": annualise(observed, row.exposure_weeks),
                    "exposure_weeks": row.exposure_weeks,
                    "population": row.population,
                    "evidence_type": row.evidence_type,
                    "source": row.source,
                    "source_url": row.source_url,
                    "vintage_year": row.vintage_year,
                    "confidence_tier": row.confidence_tier,
                }
            if per_drug:
                rows.append({
                    "ae_code": event.ae_code,
                    "ae_label": event.ae_label,
                    "is_serious": event.is_serious,
                    "unit_cost": float(unit.unit_cost_local) if unit else None,
                    "unit_cost_source": unit.source if unit else None,
                    "unit_cost_tier": unit.confidence_tier if unit else None,
                    "by_drug": per_drug,
                })

        return {"country_code": country_code, "events": rows}

    @staticmethod
    def _asymmetry_warnings(
        drug_ids: Sequence[int], country_codes: Sequence[str],
        costs: Mapping[tuple[int, str], Money],
    ) -> list[Warning_]:
        """The important one (M13 section 5.1).

        Pricing one therapy's events while leaving its comparators at zero
        inflates that therapy's apparent cost — or, with the sides reversed,
        manufactures a saving. The asymmetric case is the *natural* state of
        the data: a new asset has a recent detailed trial, while a comparator
        approved in 2010 may have a label and little else. It is a warning
        rather than an error because refusing to compute would be worse than
        computing with the caveat stated.
        """
        out: list[Warning_] = []
        for code in country_codes:
            with_profile = [d for d in drug_ids if (d, code) in costs]
            without = [d for d in drug_ids if (d, code) not in costs]
            if with_profile and without:
                out.append(Warning_(
                    code=WarningCode.AE_PROFILE_ASYMMETRIC,
                    message=(
                        f"{len(with_profile)} of {len(drug_ids)} therapies carry an "
                        "adverse-event profile; the rest are costed at zero because "
                        "none was found. This biases the comparison in favour of the "
                        "therapies without one — their event costs are missing, not "
                        "absent."
                    ),
                    country_code=code,
                ))
        return out


#: Tiers that mean the unit cost was constructed rather than observed.
_DERIVED_TIERS = frozenset({ConfidenceTier.C, ConfidenceTier.D})
