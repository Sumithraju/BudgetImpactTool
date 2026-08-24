"""Batch loaders for M0 reference data — M1 section 5.2's performance rule.

Every method here loads *all* rows for a set of markets in one query. That
is the whole point: section 5.2 calls one query per parameter per market an
N+1 defect, and the only durable way to prevent it is for the resolver to
have no session at all. It takes a pre-built `ResolutionContext`; this
module is the one place that builds it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from biet_engine.models import ConfidenceTier

from ..constants.parameter_paths import FUNNEL_STAGE_TO_PATH
from ..models.reference import (
    Country,
    CountryEconomics,
    Drug,
    DrugPrice,
    EligibilityCriterion,
    Epidemiology,
    FunnelDefault,
    FxRate,
)
from ..services.resolution import ReferenceValue, ResolutionKey

#: `epidemiology.prevalence_pct` is stored 0-100; the engine only ever sees
#: fractions (M2 section 7). Converting here, at the repository boundary, is
#: what keeps that true — non-negotiable 5.
_PCT_TO_FRACTION = 100.0


def _tier(raw: str | None) -> ConfidenceTier:
    """The *engine's* ConfidenceTier, not `biet_api.constants.domain`'s.

    The two are deliberate mirrors of each other (the engine cannot import
    `biet_api`), and `test_constants_parity.py` keeps their members in step —
    but they are distinct types, and this one feeds `Provenance`, which is an
    engine object. A missing tier reads as D: a placeholder that must be
    replaced, which is the safe reading of "we do not know".
    """
    return ConfidenceTier(raw) if raw else ConfidenceTier.D


class ReferenceRepository:
    """Reads every reference table a scenario needs, in bounded queries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ----------------------------------------------------------------- countries

    def list_countries(self, codes: Sequence[str]) -> Sequence[Country]:
        return self._session.scalars(
            select(Country).where(Country.country_code.in_(codes))
        ).all()

    def list_active_country_codes(self) -> set[str]:
        return set(
            self._session.scalars(
                select(Country.country_code).where(Country.is_active.is_(True))
            ).all()
        )

    # ----------------------------------------------------------------- economics

    def load_economics(self, codes: Sequence[str]) -> dict[ResolutionKey, ReferenceValue]:
        """`(economics.<indicator>, country) -> value`, latest vintage per pair.

        One query for every indicator and market. Where a market has more
        than one vintage for an indicator, the most recent wins — the rows
        are ordered so the later year overwrites the earlier.
        """
        rows = self._session.scalars(
            select(CountryEconomics)
            .where(CountryEconomics.country_code.in_(codes))
            .order_by(CountryEconomics.year)
        ).all()

        return {
            (f"economics.{row.indicator}", row.country_code): ReferenceValue(
                value=float(row.value),
                source=row.source,
                confidence_tier=_tier(row.confidence_tier),
                vintage_year=row.year,
            )
            for row in rows
        }

    def load_adult_share(self, codes: Sequence[str]) -> dict[ResolutionKey, ReferenceValue]:
        rows = self.list_countries(codes)
        return {
            ("countries.adult_share", row.country_code): ReferenceValue(
                value=float(row.adult_share),
                source=row.adult_share_source or "unknown",
                confidence_tier=_tier(row.adult_share_confidence_tier),
            )
            for row in rows
            if row.adult_share is not None
        }

    # ----------------------------------------------------------------- epidemiology

    def load_prevalence(
        self, codes: Sequence[str], indication_id: int,
    ) -> dict[ResolutionKey, ReferenceValue]:
        """Latest prevalence per market, converted from percent to fraction.

        Ordered by year so a projected current-year row supersedes the stale
        observed one it was projected from (M0 section 5.3).
        """
        rows = self._session.scalars(
            select(Epidemiology)
            .where(Epidemiology.country_code.in_(codes))
            .where(Epidemiology.indication_id == indication_id)
            .order_by(Epidemiology.year)
        ).all()

        return {
            ("epidemiology.prevalence", row.country_code): ReferenceValue(
                value=float(row.prevalence_pct) / _PCT_TO_FRACTION,
                low=(
                    float(row.prevalence_low) / _PCT_TO_FRACTION
                    if row.prevalence_low is not None else None
                ),
                high=(
                    float(row.prevalence_high) / _PCT_TO_FRACTION
                    if row.prevalence_high is not None else None
                ),
                source=row.source,
                confidence_tier=_tier(row.confidence_tier),
                vintage_year=row.year,
                is_projected=row.is_projected,
            )
            for row in rows
        }

    # ----------------------------------------------------------------- funnel

    def load_funnel_defaults(
        self, codes: Sequence[str], indication_id: int,
    ) -> tuple[dict[ResolutionKey, ReferenceValue], dict[ResolutionKey, ReferenceValue]]:
        """`(country_defaults, global_defaults)` for the funnel rates.

        A `funnel_defaults` row with `country_code` NULL is the
        indication-level global; one naming a market is that market's
        default. They land in different stores because they resolve at
        different levels (M1 section 5.2).
        """
        rows = self._session.scalars(
            select(FunnelDefault)
            .where(FunnelDefault.indication_id == indication_id)
            .where(
                FunnelDefault.country_code.in_(codes)
                | FunnelDefault.country_code.is_(None)
            )
        ).all()

        country: dict[ResolutionKey, ReferenceValue] = {}
        globals_: dict[ResolutionKey, ReferenceValue] = {}
        for row in rows:
            path = FUNNEL_STAGE_TO_PATH.get(row.stage)
            if path is None:
                # A stage with no override path cannot be overridden and has
                # no place in the resolution chain; skipping it here is what
                # surfaces the gap as an unresolved parameter downstream
                # rather than as a silently-ignored seed row.
                continue
            value = ReferenceValue(
                value=float(row.value),
                low=float(row.value_low) if row.value_low is not None else None,
                high=float(row.value_high) if row.value_high is not None else None,
                source=row.source,
                confidence_tier=_tier(row.confidence_tier),
            )
            key = (path, row.country_code)
            (globals_ if row.country_code is None else country)[key] = value

        return country, globals_

    # ----------------------------------------------------------------- criteria

    def list_criteria(self, indication_id: int) -> Sequence[EligibilityCriterion]:
        return self._session.scalars(
            select(EligibilityCriterion)
            .where(EligibilityCriterion.indication_id == indication_id)
            .order_by(EligibilityCriterion.criterion_id)
        ).all()

    # ----------------------------------------------------------------- therapies

    def list_drugs_with_regimens(self, indication_id: int) -> Sequence[Drug]:
        """Drugs and their regimens in one query — `selectinload` rather than
        a per-drug lazy load, which would be the N+1 the skill forbids."""
        return self._session.scalars(
            select(Drug)
            .where(Drug.indication_id == indication_id)
            .options(selectinload(Drug.regimens))
            .order_by(Drug.drug_id)
        ).all()

    def load_prices(
        self, codes: Sequence[str], drug_ids: Sequence[int],
    ) -> dict[tuple[int, str], DrugPrice]:
        """`(drug_id, country_code) -> price`, one query for the whole matrix.

        Where a drug has several bases in one market, the observed ones win
        over derived: NADAC (a real transaction price) beats list, and both
        beat a PPP derivation. `_BASIS_PRIORITY` encodes that ordering.
        """
        rows = self._session.scalars(
            select(DrugPrice)
            .where(DrugPrice.country_code.in_(codes))
            .where(DrugPrice.drug_id.in_(drug_ids))
        ).all()

        best: dict[tuple[int, str], DrugPrice] = {}
        for row in rows:
            key = (row.drug_id, row.country_code)
            incumbent = best.get(key)
            if incumbent is None or _basis_rank(row.price_basis) < _basis_rank(
                incumbent.price_basis
            ):
                best[key] = row
        return best

    # ----------------------------------------------------------------- fx

    def load_fx_snapshot(self) -> tuple[dict[str, float], date | None]:
        """The FX rate set and the date it was fetched.

        Both halves matter: non-negotiable 6 says FX is snapshotted into the
        run, and a snapshot without its vintage cannot be audited later —
        `EngineInput.fx_snapshot_date` exists precisely so the date travels
        with the rates rather than being inferred at report time.

        Ordered ascending so the latest row per currency wins; the date
        returned is the newest across all of them.
        """
        rows = self._session.scalars(
            select(FxRate).order_by(FxRate.fetched_date)
        ).all()
        rates = {row.currency_code: float(row.rate_per_usd) for row in rows}
        latest = max((row.fetched_date for row in rows), default=None)
        return rates, latest


#: Lower is preferred. NADAC is an observed acquisition cost, list is
#: published but pre-rebate, estimated_net is a stated assumption, and
#: ppp_derived is a model output rather than an observation (M5 section 5.3).
_BASIS_PRIORITY = {"nadac": 0, "list": 1, "estimated_net": 2, "ppp_derived": 3}


def _basis_rank(basis: str) -> int:
    return _BASIS_PRIORITY.get(basis, len(_BASIS_PRIORITY))
