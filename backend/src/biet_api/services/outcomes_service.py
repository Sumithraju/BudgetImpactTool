"""Clinical outcomes — M16, the impure half.

Resolves stored trial evidence into the `TreatmentEffect` and `ResponseProfile`
the pure engine consumes, and decides what an *absence* means. The arithmetic
— events avoided, effect retained, cost offset — lives in
`biet_engine.outcomes` and knows nothing about databases, markets or FX.

Two decisions live here rather than in the engine, because both need data the
engine does not have:

**Where the baseline rate comes from.** A relative risk reduction is a property
of the therapy; the rate it applies to is a property of the population. This
service joins the two, which is why an effect observed once in SELECT produces
a tenfold-different avoided-event count in secondary prevention than in obesity
without cardiovascular disease.

**What an unpriced market does.** Only the reference market carries cited event
costs. Every other market derives its cost through the same purchasing-power
path M5 uses for an unpriced therapy, labelled derived and warned about —
rather than being seeded with placeholder figures that would look observed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from biet_engine.constants import (
    PPP_DEFAULT_ELASTICITY,
    PPP_PRICE_FLOOR,
    REFERENCE_MARKET,
    EventClass,
    ResponseThreshold,
)
from biet_engine.cost import derive_ppp_price
from biet_engine.fx import convert
from biet_engine.models import (
    ConfidenceTier,
    Money,
    Provenance,
    ResolutionLevel,
    ResponseProfile,
    TreatmentEffect,
    Valued,
    Warning_,
)

from ..constants.domain import WarningCode
from ..exceptions import ValidationError
from ..models.outcomes import DiseaseSubgroup
from ..models.outcomes import ResponseProfile as ResponseProfileRow
from ..models.outcomes import TreatmentEffect as TreatmentEffectRow
from ..repositories.outcomes import OutcomesRepository

#: The responder threshold every trial in this class reports, and therefore
#: the only one comparable across them.
COMPARABLE_THRESHOLD = ResponseThreshold.WL_5


@dataclass(frozen=True)
class Baseline:
    """One event class's annual rate in a population, however composed.

    `covered_share` is the fraction of that population the rate was actually
    observed in. It is 1.0 for a single segment and less when segments were
    combined and some had no row — which the caller reports rather than
    absorbing, because a rate observed in four fifths of a population and
    applied to all of it is a stated approximation, not a measurement.
    """

    value: float
    low: float | None
    high: float | None
    covered_share: float
    confidence_tier: str
    vintage_year: int | None
    source: str


def _f(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


class OutcomesService:
    """Trial evidence, resolved per therapy per market per subgroup."""

    def __init__(self, session: Session) -> None:
        self._repo = OutcomesRepository(session)

    # ------------------------------------------------------------- subgroups

    def list_subgroups(self, indication_id: int) -> Sequence[DiseaseSubgroup]:
        return self._repo.list_subgroups(indication_id)

    def resolve_subgroups(
        self, indication_id: int, codes: Sequence[str],
    ) -> tuple[list[DiseaseSubgroup], tuple[Warning_, ...]]:
        """The segments a run covers, in presentation order.

        An empty `codes` means the whole diagnosed population, which this
        returns as an empty list — the caller then takes its single
        un-segmented pass, exactly as every run did before subgroups existed.

        **Selecting more than one overlapping subgroup is refused.** The
        WHO-derived obesity subgroups share patients: a patient with both
        diabetes and hypertension is in two of them, and across the ten source
        countries the four shares sum to about 1.5x the obese population. Adding
        their results would overstate the treated population by half, and
        nothing in the arithmetic would complain. They are alternative
        eligibility definitions to compare, so the model compares them one at a
        time and the comparison view runs each independently.

        Raises:
            ValidationError: more than one overlapping subgroup was selected.
        """
        if not codes:
            return [], ()

        available = self._repo.subgroups_by_code(indication_id, [])
        wanted = set(codes)
        selected = [s for s in available.values() if s.subgroup_code in wanted]
        selected.sort(key=lambda s: (s.sort_order, s.subgroup_code))

        overlapping = [s for s in selected if s.is_overlapping]
        if len(overlapping) > 1:
            names = ", ".join(s.subgroup_label for s in overlapping)
            raise ValidationError(
                f"{names} overlap — a patient can be in more than one of them, so "
                "their results cannot be added without counting that patient twice. "
                "Model one at a time; the Subgroups tab compares all of them side by "
                "side, each run on its own.",
                field="subgroup_codes",
            )

        unknown = sorted(wanted - set(available))
        warnings: list[Warning_] = []
        if unknown:
            warnings.append(Warning_(
                code=WarningCode.SUBGROUP_SHARES_UNBALANCED,
                message=(
                    f"No subgroup named {', '.join(unknown)} exists for this disease, "
                    "so it contributes nothing to the result. Check the code rather "
                    "than reading the total as complete."
                ),
            ))

        covered = math.fsum(float(s.share_of_diagnosed) for s in selected)
        if selected and covered < 1.0 - 1e-6:
            warnings.append(Warning_(
                code=WarningCode.SUBGROUP_SHARES_UNBALANCED,
                message=(
                    f"This run models {covered:.1%} of the prevalent disease "
                    "population — the share that meets this subgroup's clinical "
                    "definition. Every population and cost figure below is for that "
                    "share only, and is not comparable with a whole-population run "
                    "without saying so."
                ),
            ))
        return selected, tuple(warnings)

    def combined_segment(
        self, segments: Sequence[DiseaseSubgroup],
    ) -> DiseaseSubgroup | None:
        """One synthetic segment standing for a selection of several.

        The forward calculation runs the engine once per segment and adds the
        results up. The *analyses* cannot: a tornado, a Monte Carlo and a
        price solve are each defined over one engine input, and running them
        per segment would produce six tornadoes nobody asked for.

        So they run over a single input built from the union — share is the sum
        of the selected shares, and the two per-segment factors are averaged
        weighted by share, since a segment covering a quarter of the population
        should count for a quarter of the combined adjustment.

        Without this the analyses would silently describe the *whole* diagnosed
        population while the headline described a subset of it, and a credible
        interval quoted around a point estimate it does not contain is worse
        than no interval at all.

        Returned transient — never added to the session. It is a calculation
        input, not a record; persisting it would put a derived row in a
        catalogue of curated ones.
        """
        if not segments:
            return None
        if len(segments) == 1:
            return segments[0]

        total_share = math.fsum(float(s.share_of_diagnosed) for s in segments)
        if total_share <= 0:
            return None

        def weighted(attribute: str) -> float:
            return math.fsum(
                float(getattr(s, attribute)) * float(s.share_of_diagnosed)
                for s in segments
            ) / total_share

        labels = ", ".join(s.subgroup_label for s in segments)
        return DiseaseSubgroup(
            indication_id=segments[0].indication_id,
            subgroup_code="+".join(s.subgroup_code for s in segments),
            subgroup_label=f"{len(segments)} segments combined",
            description=labels,
            share_of_diagnosed=Decimal(str(round(min(total_share, 1.0), 5))),
            eligible_factor=Decimal(str(round(weighted("eligible_factor"), 4))),
            uptake_multiplier=Decimal(str(round(weighted("uptake_multiplier"), 4))),
            sort_order=0,
            source=(
                "Share-weighted combination of the selected segments, built so "
                "the sensitivity analyses describe the same population as the "
                "headline figure: " + labels
            ),
            # The weakest tier among the segments combined. A combination is no
            # better founded than its worst component.
            confidence_tier=max(
                (str(s.confidence_tier) for s in segments), default="C",
            ),
        )

    def baseline_rates(
        self, segments: Sequence[DiseaseSubgroup],
    ) -> dict[str, Baseline]:
        """`event_class -> annual rate` for a population made of these segments.

        One segment is its own rates. Several are share-weighted, and the
        weighting rule is the interesting part: **a segment with no row for an
        event contributes a zero, not an absence.**

        That is right for the data this models rather than a convenience. The
        obesity-with-diabetes segment has no incident-diabetes row because
        those patients already have diabetes — they genuinely cannot
        contribute new cases. Averaging only over the segments that *can*
        would return the rate among the susceptible and then apply it to
        everybody, overstating avoided cases by the share of the population
        that was never at risk.

        Where the zero means "no data" rather than "cannot occur", the reader
        needs to know, so `covered_share` records what fraction of the
        population the rate was actually observed in and the caller surfaces
        it.
        """
        if not segments:
            return {}

        total_share = math.fsum(float(s.share_of_diagnosed) for s in segments)
        if total_share <= 0:
            return {}

        rows_by_segment = {
            s.subgroup_id: self._repo.baseline_rates(s.subgroup_id)
            for s in segments
            if s.subgroup_id is not None
        }
        classes = {
            event
            for rows in rows_by_segment.values()
            for event in rows
        }

        out: dict[str, Baseline] = {}
        for event in classes:
            weighted = 0.0
            covered = 0.0
            sources: list[str] = []
            tiers: list[str] = []
            vintage: int | None = None
            low_terms: list[float] = []
            high_terms: list[float] = []
            for segment in segments:
                row = rows_by_segment.get(segment.subgroup_id, {}).get(event)
                if row is None:
                    continue
                share = float(segment.share_of_diagnosed)
                weighted += float(row.baseline_annual_rate) * share
                low_terms.append(float(row.rate_low or row.baseline_annual_rate) * share)
                high_terms.append(float(row.rate_high or row.baseline_annual_rate) * share)
                covered += share
                sources.append(row.source)
                tiers.append(str(row.confidence_tier))
                vintage = vintage or row.vintage_year

            if covered <= 0:
                continue
            out[event] = Baseline(
                value=weighted / total_share,
                low=math.fsum(low_terms) / total_share if low_terms else None,
                high=math.fsum(high_terms) / total_share if high_terms else None,
                covered_share=covered / total_share,
                # The weakest tier among the rows combined. A share-weighted
                # average is no better founded than its worst component.
                confidence_tier=max(tiers) if tiers else "C",
                vintage_year=vintage,
                source=(
                    sources[0] if len(set(sources)) == 1
                    else (
                        f"Share-weighted across {len(sources)} segments. "
                        + sources[0]
                    )
                ),
            )
        return out

    def country_share(
        self, subgroup: DiseaseSubgroup, country_code: str,
    ) -> tuple[float, float, str, str]:
        """One subgroup's share and eligibility in one market.

        Returns `(share, eligible_factor, source, tier)`, preferring the
        market's own WHO-derived figure over the cross-market mean. The
        difference is not cosmetic: the hypertension subgroup is 56% of obese
        adults in Brazil and 43% in France because their published hypertension
        prevalences differ by a third, and one global figure would apply
        Brazil's comorbidity burden to France.
        """
        for rate in subgroup.country_rates:
            if str(rate.country_code) == country_code:
                return (
                    float(rate.share_of_diagnosed),
                    float(rate.eligible_factor),
                    rate.source,
                    str(rate.confidence_tier),
                )
        return (
            float(subgroup.share_of_diagnosed),
            float(subgroup.eligible_factor),
            (
                f"No market-specific figure for {country_code}; using the mean across "
                f"the markets that have one. {subgroup.source}"
            ),
            # A mean standing in for a market-specific value is weaker than the
            # values it averages, and says so.
            "C",
        )

    # ------------------------------------------------------------- effects

    def resolve_effects(
        self,
        *,
        drug_id: int,
        segments: Sequence[DiseaseSubgroup],
        label: str,
        country_codes: Sequence[str],
        currencies: Mapping[str, str],
        gdp_pc_ppp: Mapping[str, float],
        fx_rates: Mapping[str, float],
    ) -> tuple[dict[str, list[TreatmentEffect]], tuple[Warning_, ...]]:
        """`country_code -> [effect, ...]` for one therapy in one population.

        `segments` is a single segment for a segmented pass, and every segment
        of the disease for an un-segmented one — because the whole diagnosed
        population is a population too, and it has a baseline event rate that
        is the share-weighted average of its parts. Passing an empty sequence
        here would report "no effect published", which is a claim about the
        evidence rather than about the data shape, and false.

        An event is modelled only when all three of its parts are present: the
        therapy has a published reduction for it, the population has a baseline
        rate for it, and the market has a cost for it (observed or derived).
        A missing baseline rate drops the event silently and correctly — the
        obesity-with-diabetes segment cannot avoid incident diabetes — while a
        missing cost is warned about, because there the event *does* occur and
        is simply priced at nothing.
        """
        effects_by_drug = self._repo.load_effects([drug_id])
        rows = effects_by_drug.get(drug_id, [])
        if not rows or not segments:
            # No supplied effect, or no population to supply a baseline rate.
            # Both are handled by the engine's own `NO_OUTCOME_EVIDENCE`.
            return {code: [] for code in country_codes}, ()

        baselines = self.baseline_rates(segments)
        observed = self._repo.load_event_costs(list(country_codes))
        reference = self._repo.reference_event_costs(REFERENCE_MARKET)

        out: dict[str, list[TreatmentEffect]] = {code: [] for code in country_codes}
        derived_markets: set[str] = set()
        unpriced: dict[str, set[str]] = {}
        transported: set[str] = set()
        partial: dict[str, float] = {}
        segment_codes = {s.subgroup_code for s in segments}

        for code in country_codes:
            currency = currencies[code]
            for row in rows:
                baseline = baselines.get(row.event_class)
                if baseline is None:
                    continue

                cost, was_derived = self._event_cost(
                    row.event_class, code, currency, observed, reference,
                    gdp_pc_ppp, fx_rates,
                )
                if cost is None:
                    unpriced.setdefault(code, set()).add(row.event_class)
                    continue
                if was_derived:
                    derived_markets.add(code)

                if (
                    row.observed_in_subgroup
                    and row.observed_in_subgroup not in segment_codes
                ):
                    transported.add(f"{row.event_class} ({row.trial})")
                if baseline.covered_share < 1.0 - 1e-9:
                    partial[row.event_class] = baseline.covered_share

                out[code].append(TreatmentEffect(
                    drug_id=drug_id,
                    event=EventClass(row.event_class),
                    baseline_rate=Valued(
                        value=baseline.value,
                        low=baseline.low,
                        high=baseline.high,
                        provenance=Provenance(
                            source=baseline.source,
                            vintage_year=baseline.vintage_year,
                            confidence_tier=ConfidenceTier(baseline.confidence_tier),
                            resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
                            note=f"baseline rate in {label}",
                        ),
                    ),
                    relative_reduction=Valued(
                        value=float(row.relative_reduction),
                        low=_f(row.reduction_low),
                        high=_f(row.reduction_high),
                        provenance=self._effect_provenance(row),
                    ),
                    unit_cost=cost,
                    trial=row.trial,
                    follow_up_weeks=row.follow_up_weeks,
                ))

        warnings: list[Warning_] = []
        if derived_markets:
            warnings.append(Warning_(
                code=WarningCode.AE_COST_DERIVED,
                message=(
                    "Avoided-event costs in "
                    f"{', '.join(sorted(derived_markets))} are derived from the "
                    f"{REFERENCE_MARKET} figure through purchasing-power parity rather "
                    "than observed locally. The cost offset in those markets is a "
                    "modelling assumption, not a national tariff."
                ),
            ))
        for code, events in sorted(unpriced.items()):
            warnings.append(Warning_(
                code=WarningCode.EVENT_COST_MISSING,
                message=(
                    f"{', '.join(sorted(events))} has no unit cost in {code} and none "
                    "could be derived, so events of that class are counted but valued "
                    "at nothing. The saving they represent is missing from this result, "
                    "not absent from the world."
                ),
                country_code=code,
            ))
        if transported:
            warnings.append(Warning_(
                code="EFFECT_TRANSPORTED",
                message=(
                    f"{', '.join(sorted(transported))} was observed in a different "
                    f"population from {label}. Applying it here assumes the relative "
                    "reduction transports across populations, which the trial does "
                    "not establish."
                ),
            ))
        for event, covered in sorted(partial.items()):
            warnings.append(Warning_(
                code="BASELINE_RATE_PARTIAL",
                message=(
                    f"The baseline rate for {event} is observed in {covered:.0%} of "
                    f"{label} and applied across all of it. The segments without a "
                    "rate contribute zero to the average, which is right where they "
                    "cannot experience the event and an understatement where the rate "
                    "is simply unknown."
                ),
            ))
        return out, tuple(warnings)

    @staticmethod
    def _effect_provenance(row: TreatmentEffectRow) -> Provenance:
        return Provenance(
            source=row.source,
            vintage_year=row.vintage_year,
            confidence_tier=ConfidenceTier(row.confidence_tier),
            resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
            note=f"{row.trial}{f' ({row.nct_id})' if row.nct_id else ''}",
        )

    def _event_cost(
        self,
        event_class: str,
        country_code: str,
        currency: str,
        observed: Mapping[tuple[str, str], object],
        reference: Mapping[str, object],
        gdp_pc_ppp: Mapping[str, float],
        fx_rates: Mapping[str, float],
    ) -> tuple[Money | None, bool]:
        """The market's cost for one event class, and whether it was derived.

        Derivation runs in USD and converts back, matching M5: the
        purchasing-power formula is defined on USD-normalised values, and
        scaling a local-currency figure by a PPP ratio would apply the
        exchange rate twice.
        """
        row = observed.get((event_class, country_code))
        if row is not None:
            return (
                Money(
                    amount=float(row.unit_cost_local),  # type: ignore[attr-defined]
                    currency=str(row.currency_code),    # type: ignore[attr-defined]
                ),
                False,
            )

        ref = reference.get(event_class)
        target_ppp = gdp_pc_ppp.get(country_code)
        ref_ppp = gdp_pc_ppp.get(REFERENCE_MARKET)
        if ref is None or target_ppp is None or ref_ppp is None or ref_ppp <= 0:
            return None, False

        ref_usd = convert(
            Money(
                amount=float(ref.unit_cost_local),   # type: ignore[attr-defined]
                currency=str(ref.currency_code),     # type: ignore[attr-defined]
            ),
            "USD", fx_rates,
        )
        derived_usd = derive_ppp_price(
            ref_usd.amount, target_ppp, ref_ppp,
            PPP_DEFAULT_ELASTICITY, PPP_PRICE_FLOOR,
        )
        return convert(Money(amount=derived_usd, currency="USD"), currency, fx_rates), True

    # ------------------------------------------------------------- profiles

    def resolve_profile(
        self, drug_id: int, *, regain_override: float | None = None,
    ) -> ResponseProfile | None:
        """The therapy's responder profile, or None when none is published.

        `regain_override` replaces the seeded annual regain. It is a scenario
        lever rather than an observation — the seeded zero rests on trials
        that maintained the effect on continuous therapy, and a payer who does
        not accept that reading needs to be able to say so and watch every
        avoided-event count from year 2 fall.
        """
        row = self._repo.load_profiles([drug_id]).get(drug_id)
        if row is None:
            return None
        return self._to_engine_profile(row, regain_override)

    @staticmethod
    def _to_engine_profile(
        row: ResponseProfileRow, regain_override: float | None,
    ) -> ResponseProfile:
        seeded_regain = float(row.regain_per_year)
        regain = seeded_regain if regain_override is None else regain_override
        provenance = Provenance(
            source=row.source,
            vintage_year=row.vintage_year,
            confidence_tier=ConfidenceTier(row.confidence_tier),
            resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
            note=f"{row.trial}{f' ({row.nct_id})' if row.nct_id else ''}",
        )
        regain_provenance = (
            provenance if regain_override is None
            else Provenance(
                source=(
                    "Scenario override. The seeded value of "
                    f"{seeded_regain:.1%} a year rests on the maintenance data in "
                    f"{row.trial}; this run replaces it."
                ),
                confidence_tier=ConfidenceTier.C,
                resolution_level=ResolutionLevel.SCENARIO_OVERRIDE,
            )
        )
        return ResponseProfile(
            drug_id=row.drug_id,
            threshold=ResponseThreshold(row.threshold),
            responder_share=Valued(
                value=float(row.responder_share),
                low=_f(row.responder_low),
                high=_f(row.responder_high),
                provenance=provenance,
            ),
            mean_weight_loss_pct=Valued(
                value=float(row.mean_weight_loss_pct), provenance=provenance,
            ),
            regain_per_year=Valued(value=regain, provenance=regain_provenance),
            trial=row.trial,
        )
