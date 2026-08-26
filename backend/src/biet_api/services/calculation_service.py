"""Runs the engine and maps its output to the HTTP contract.

The engine is called here and nowhere else in the API. It receives a fully
resolved `EngineInput` and returns frozen results; this module's only job is
to invoke it, persist the run, and translate the result into response
schemas. No calculation happens in this file.
"""

from __future__ import annotations

import math
import time
import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from biet_engine import __version__ as engine_version
from biet_engine.affordability import compute_affordability
from biet_engine.cost import compute_therapy_cost
from biet_engine.impact import compute_budget_impact
from biet_engine.models import (
    CountryInput,
    CountryResult,
    EngineInput,
    EngineResult,
    OutcomeResult,
    Provenance,
    ResponseProfile,
    TherapyInput,
    Warning_,
)
from biet_engine.models import TreatmentEffect as EngineTreatmentEffect
from biet_engine.outcomes import project_outcomes
from biet_engine.persistence import persistence_fraction
from biet_engine.psa import run_psa
from biet_engine.safety import build_cost_bridge
from biet_engine.sensitivity import run_owsa

from ..constants.domain import EVENT_LABELS, RunType
from ..models.outcomes import DiseaseSubgroup
from ..schemas.calculation import (
    AffordabilityRead,
    AvoidedEventRead,
    BreakEvenResponse,
    BridgeTermRead,
    CalculationResponse,
    CostBridgeRead,
    CountryRead,
    CriterionRead,
    FunnelStageRead,
    OutcomesRead,
    OwsaEntryRead,
    OwsaResponse,
    ProvenanceRead,
    PsaResponse,
    SubgroupResultRead,
    TherapyRead,
    TotalsRead,
    UptakeScenarioResponse,
    WarningRead,
    YearRead,
)
from . import segmentation
from .engine_input import EngineInputBuilder
from .epidemiology_service import EpidemiologyService
from .outcomes_service import OutcomesService
from .payer_service import PayerService, aggregate_country_payer

#: Buckets for the PSA histogram. Enough shape to read the skew, few enough
#: that the payload stays small — the interface never plots raw samples.
PSA_HISTOGRAM_BINS = 36

DEFAULT_PSA_ITERATIONS = 5_000
DEFAULT_PSA_SEED = 20_260_906


def _provenance(p: Provenance | None) -> ProvenanceRead | None:
    if p is None:
        return None
    return ProvenanceRead(
        source=p.source, vintage_year=p.vintage_year,
        confidence_tier=str(p.confidence_tier),
        resolution_level=str(p.resolution_level),
        is_projected=p.is_projected, note=p.note,
    )


def _require(provenance: ProvenanceRead | None) -> ProvenanceRead:
    """Narrow an optional provenance that the caller knows is present.

    `_provenance` is optional-in, optional-out because most of its callers
    genuinely have nothing. A `Valued`'s provenance is non-optional by
    contract, so this asserts rather than substituting a placeholder — a
    fabricated source is the one thing this system must never emit.
    """
    assert provenance is not None
    return provenance


def _warnings(items: Sequence[Warning_]) -> list[WarningRead]:
    return [
        WarningRead(
            code=w.code, message=w.message,
            country_code=w.country_code, parameter_path=w.parameter_path,
        )
        for w in items
    ]


def _bridge(ci: CountryInput) -> CostBridgeRead:
    """The net cost per switch, decomposed (M13 section 5.3).

    Computed from the same resolved inputs M7 used, so it cannot diverge from
    the `net_cost_per_switch` already in every year of the response — a
    golden test asserts the two reconcile.
    """
    persistence = {
        t.drug_id: persistence_fraction(t.persistence_12m.value)
        for t in (ci.new_therapy, *ci.therapies)
    }
    bridge = build_cost_bridge(
        compute_therapy_cost(ci.new_therapy, ci.country_code),
        [compute_therapy_cost(t, ci.country_code) for t in ci.therapies],
        substitution={k: v.value for k, v in ci.substitution.shares.items()},
        persistence=persistence,
        country_code=ci.country_code,
    )
    return CostBridgeRead(
        terms=[
            BridgeTermRead(
                component=str(term.component),
                new_therapy=term.new_therapy.amount,
                displaced=term.displaced.amount,
                delta=term.delta.amount,
            )
            for term in bridge.terms
        ],
        net_cost_per_switch=bridge.net_cost_per_switch.amount,
    )


def _therapy(t: TherapyInput, currency: str) -> TherapyRead:
    prov = _provenance(t.price_provenance)
    assert prov is not None            # TherapyInput.price_provenance is non-optional
    return TherapyRead(
        drug_id=t.drug_id, name=t.name, is_new=t.is_new,
        unit_price=t.unit_price.amount, currency=currency,
        price_basis=str(t.price_basis), provenance=prov,
        persistence_12m=t.persistence_12m.value,
    )


#: M16. The scenario override that replaces a therapy's seeded weight-regain
#: assumption. Not in M1's original vocabulary because M16 did not exist when
#: that vocabulary was written; declared in `parameter_paths` alongside the
#: rest so it validates like any other override rather than being read raw.
REGAIN_PATH = "outcomes.regain_per_year"


def _regain_override(scenario: object) -> float | None:
    """The scenario's weight-regain override, if it set one.

    Read directly off the scenario rather than through the resolver because it
    is not a market-level value: regain is a property of the therapy and the
    assumption a reader is making about it, identical in every market.
    """
    for override in getattr(scenario, "overrides", ()) or ():
        if override.parameter_path == REGAIN_PATH:
            try:
                return float(override.value)
            except (TypeError, ValueError):
                return None
    return None


def _deduplicate(warnings: Sequence[Warning_]) -> list[Warning_]:
    """Collapse warnings repeated across segments.

    A segmented run calls the same resolution path once per segment, so a
    market-level warning — a stale vintage, a mixed price basis — would appear
    six times identically. Six identical rows is a list a reader stops reading,
    which costs the warning the attention it was raised to get.
    """
    seen: set[tuple[str, str, str | None]] = set()
    out: list[Warning_] = []
    for warning in warnings:
        key = (warning.code, warning.message, warning.country_code)
        if key in seen:
            continue
        seen.add(key)
        out.append(warning)
    return out


def _outcomes_read(
    outcome: OutcomeResult,
    effects: Sequence[EngineTreatmentEffect],
    profile: ResponseProfile | None,
    currency: str,
) -> OutcomesRead:
    """The engine's outcome result, in the shape the interface needs.

    The engine returns one `AvoidedEvents` row per event *per year*; the
    interface reads one row per event with a year vector. Regrouped here rather
    than in the engine, because the engine's shape is the one its own
    arithmetic wants and this one is the one a table wants.

    `effects` is the same sequence that was fed to the engine, and it is passed
    in rather than reconstructed. The engine's `AvoidedEvents` reports counts,
    not the rate and reduction that produced them — and a reader shown "412
    cardiovascular events avoided" without the 2.4% baseline and the 20%
    reduction behind it cannot tell whether the model is describing secondary
    prevention or primary. Reporting those two figures as zero would be worse
    than omitting them.
    """
    by_effect = {str(effect.event): effect for effect in effects}
    by_event: dict[str, list[object]] = {}
    for row in outcome.avoided:
        by_event.setdefault(str(row.event), []).append(row)

    events: list[AvoidedEventRead] = []
    for event_class, rows in by_event.items():
        ordered = sorted(rows, key=lambda r: r.year)  # type: ignore[attr-defined]
        head = ordered[0]
        effect = by_effect.get(event_class)
        if effect is None:
            # Cannot happen through `_segment_outcomes`, which builds both
            # sides from one list. Skipped rather than filled with zeros, so a
            # future caller that does get this wrong loses a row instead of
            # publishing a fabricated rate.
            continue
        events.append(AvoidedEventRead(
            event_class=event_class,
            label=EVENT_LABELS.get(event_class, event_class),
            trial=head.trial,                                  # type: ignore[attr-defined]
            baseline_annual_rate=effect.baseline_rate.value,
            relative_reduction=effect.relative_reduction.value,
            events_without_by_year=[
                r.events_without for r in ordered                # type: ignore[attr-defined]
            ],
            avoided_by_year=[r.avoided for r in ordered],       # type: ignore[attr-defined]
            cost_avoided_by_year=[
                r.cost_avoided.amount for r in ordered           # type: ignore[attr-defined]
            ],
            total_avoided=math.fsum(
                r.avoided for r in ordered                       # type: ignore[attr-defined]
            ),
            total_cost_avoided=math.fsum(
                r.cost_avoided.amount for r in ordered           # type: ignore[attr-defined]
            ),
            baseline_provenance=_require(
                _provenance(effect.baseline_rate.provenance)
            ),
            effect_provenance=_require(
                _provenance(effect.relative_reduction.provenance)
            ),
        ))

    return OutcomesRead(
        country_code=outcome.country_code,
        currency=currency,
        responders_by_year=(
            list(outcome.responders) if outcome.responders is not None else None
        ),
        mean_weight_loss_pct=outcome.mean_weight_loss_pct,
        responder_threshold=str(profile.threshold) if profile else None,
        responder_trial=profile.trial if profile else None,
        regain_per_year=profile.regain_per_year.value if profile else None,
        events=sorted(events, key=lambda e: -e.total_cost_avoided),
        total_cost_avoided=math.fsum(m.amount for m in outcome.total_cost_avoided),
        total_cost_avoided_by_year=[m.amount for m in outcome.total_cost_avoided],
        warnings=_warnings(outcome.warnings),
    )


class CalculationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._builder = EngineInputBuilder(session)
        self._outcomes = OutcomesService(session)
        self._payer = PayerService(session)
        self._epidemiology = EpidemiologyService(session)

    def build_input(self, scenario: object) -> tuple[EngineInput, tuple[Warning_, ...]]:
        """Resolve a scenario without calculating — for callers like the
        solver that drive the engine themselves.

        Segment-aware: a run covering a subset of the disease is resolved
        against that subset, not against the whole of it. Everything built on
        this — the tornado, the Monte Carlo, the price corridor, break-even —
        would otherwise describe a population the headline figure does not.
        """
        return self._builder.build(
            scenario, subgroup=self._analysis_segment(scenario),  # type: ignore[arg-type]
        )

    def _analysis_segment(self, scenario: object) -> DiseaseSubgroup | None:
        """The one segment the single-input analyses run over.

        The forward pass runs the engine once per segment and adds the results
        up. A tornado cannot: it is defined over one engine input, and six of
        them is not an answer to the question the tornado is asked. So the
        analyses run over a share-weighted union of whatever segments the run
        covers — which is the whole population when none were selected, and is
        exactly the selected subset when some were.
        """
        segments, _ = self._outcomes.resolve_subgroups(
            scenario.indication_id,                       # type: ignore[attr-defined]
            list(getattr(scenario, "subgroup_codes", None) or []),
        )
        return self._outcomes.combined_segment(segments)

    # ----------------------------------------------------------------- forward

    def calculate(
        self, scenario: object, *, project_landscape: bool = False,
    ) -> tuple[CalculationResponse, EngineInput, EngineResult]:
        """Forward run: funnel through incremental budget impact.

        `project_landscape` admits M14's pipeline entrants into the
        world-without. Off by default and never implicit: it changes what the
        new asset is compared against, on assumptions the evidence does not
        supply.

        **Subgroups (M18) run through the same path, once per segment.** The
        engine is never told a segment exists — `EngineInputBuilder` expresses
        one as two criteria and an uptake multiplier, and `segmentation`
        reassembles the results. A scenario with no segments selected takes
        exactly the single pass it always did, so the un-segmented case has not
        become a special case of the segmented one.

        Returns the response alongside the raw engine input and result, so a
        caller that also wants sensitivity does not rebuild and recompute. When
        several segments ran, the *base* segment's input and result are
        returned — sensitivity and PSA are defined on one engine input, and
        running them per segment would answer a different question from the one
        the tornado is asked.
        """
        started = time.perf_counter()

        segments, segment_warnings = self._outcomes.resolve_subgroups(
            scenario.indication_id,           # type: ignore[attr-defined]
            list(getattr(scenario, "subgroup_codes", None) or []),
        )
        passes: list[DiseaseSubgroup | None] = list(segments) or [None]

        # A run with no segments selected still needs baseline event rates,
        # because a baseline rate is a property of the population and the whole
        # diagnosed population is one. Its rate is the share-weighted average
        # of its segments', which is exactly what `combined_segment` builds.
        #
        # Without this an un-segmented run would report no avoided events at
        # all and say the effect was unpublished — which is false. The effect
        # is published; it was the *population* that had no rate attached, and
        # reporting a data-shape gap as an absence of evidence is precisely the
        # confusion M16 exists to prevent.
        all_segments = list(
            self._outcomes.list_subgroups(scenario.indication_id)  # type: ignore[attr-defined]
        )

        per_segment_countries: list[list[CountryRead]] = []
        per_segment_totals: list[TotalsRead] = []
        subgroup_results: list[SubgroupResultRead] = []
        all_warnings: list[Warning_] = list(segment_warnings)

        base_input: EngineInput | None = None
        base_result: EngineResult | None = None

        for segment in passes:
            engine_input, resolution_warnings = self._builder.build(
                scenario, project_landscape=project_landscape, subgroup=segment,  # type: ignore[arg-type]
            )
            result = compute_budget_impact(engine_input)
            affordability = compute_affordability(result, engine_input)
            by_code = {a.country_code: a for a in affordability}

            outcomes, outcome_warnings = self._segment_outcomes(
                scenario, engine_input, result,
                # A segmented pass resolves rates from its own segment; an
                # un-segmented one from every segment, share-weighted, because
                # the whole diagnosed population is a population too.
                [segment] if segment is not None else all_segments,
            )
            countries = [
                self._country(
                    cr, engine_input, by_code.get(cr.country_code),
                    outcomes.get(cr.country_code),
                )
                for cr in result.countries
            ]

            per_segment_countries.append(countries)
            per_segment_totals.append(TotalsRead(
                by_year=[m.amount for m in result.totals.by_year],
                cumulative=result.totals.cumulative.amount,
                peak_year=result.totals.peak_year,
                currency=result.totals.cumulative.currency,
            ))

            if segment is not None:
                subgroup_results.append(
                    self._subgroup_row(segment, countries, per_segment_totals[-1])
                )

            # Resolution warnings are identical across segments by
            # construction — they describe the market data, which the segment
            # does not touch — so only the first pass contributes them. The
            # engine's own warnings can differ per segment and all are kept.
            if base_input is None:
                base_input, base_result = engine_input, result
                all_warnings.extend(resolution_warnings)
            all_warnings.extend(result.warnings)
            all_warnings.extend(outcome_warnings)

        assert base_input is not None and base_result is not None

        countries = segmentation.aggregate_countries(per_segment_countries)
        totals = segmentation.aggregate_totals(per_segment_totals)
        perspective = str(getattr(scenario, "perspective", None) or "health_system")
        covered = getattr(scenario, "covered_population", None)

        epidemiology = self._epidemiology.build(
            indication_id=scenario.indication_id,   # type: ignore[attr-defined]
            countries=base_input.countries,
            results=countries,
        )
        for country in countries:
            country.payer = aggregate_country_payer(
                country, perspective=perspective, covered_population=None,
            )
            country.epidemiology = epidemiology.get(country.country_code)

        response = CalculationResponse(
            scenario_id=base_input.scenario_id,
            engine_version=base_result.engine_version,
            reporting_currency=base_result.reporting_currency,
            fx_snapshot_date=base_result.fx_snapshot_date,
            launch_year=base_input.launch_year,
            horizon_years=base_input.horizon_years,
            countries=countries,
            totals=totals,
            subgroups=subgroup_results,
            perspective=perspective,
            warnings=_warnings(_deduplicate(all_warnings)),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        payer_view = self._payer.aggregate_payer_view(
            response, perspective=perspective, covered_population=covered,
            fx_rates=dict(base_input.fx_rates),
        )
        response.payer = payer_view
        if payer_view is not None and payer_view.covered_population_is_assumed:
            response.warnings.append(WarningRead(
                code="COVERED_POPULATION_ASSUMED",
                message=(
                    "No covered population was given for a "
                    f"{payer_view.perspective_label.lower()} perspective, so the "
                    "modelled population stands in. Every per-member figure is "
                    "therefore a population average rather than this payer's own — "
                    "enter covered lives to make them the payer's."
                ),
            ))
        return response, base_input, base_result

    # ----------------------------------------------------------------- outcomes

    def _segment_outcomes(
        self,
        scenario: object,
        engine_input: EngineInput,
        result: EngineResult,
        segments: Sequence[DiseaseSubgroup],
    ) -> tuple[dict[str, OutcomesRead], list[Warning_]]:
        """M16, per market, for one segment.

        The engine does the arithmetic; everything here is resolution and
        translation. Exposure is the patients on the new therapy, and the
        engine adjusts it for persistence itself — an effect accrues only while
        a patient is on therapy, and counting a discontinued patient as a
        responder overstates the clinical result and the economic one together.
        """
        if not engine_input.countries:
            return {}, []

        new_therapy = engine_input.countries[0].new_therapy
        currencies = {c.country_code: c.currency for c in engine_input.countries}
        gdp = {
            c.country_code: c.gdp_pc_ppp.value for c in engine_input.countries
        }
        regain = _regain_override(scenario)
        profile = self._outcomes.resolve_profile(
            new_therapy.drug_id, regain_override=regain,
        )
        effects_by_country, warnings = self._outcomes.resolve_effects(
            drug_id=new_therapy.drug_id,
            segments=segments,
            label=(
                segments[0].subgroup_label if len(segments) == 1
                else "the whole diagnosed population"
            ),
            country_codes=list(currencies),
            currencies=currencies,
            gdp_pc_ppp=gdp,
            fx_rates=dict(engine_input.fx_rates),
        )

        out: dict[str, OutcomesRead] = {}
        collected: list[Warning_] = list(warnings)
        for country_result in result.countries:
            code = country_result.country_code
            country_input = next(
                c for c in engine_input.countries if c.country_code == code
            )
            treated = [year.patients_on_new for year in country_result.years]
            outcome = project_outcomes(
                treated,
                effects_by_country.get(code, []),
                profile,
                persistence=persistence_fraction(
                    country_input.new_therapy.persistence_12m.value
                ),
                country_code=code,
                currency=country_input.currency,
            )
            collected.extend(outcome.warnings)
            out[code] = _outcomes_read(
                outcome, effects_by_country.get(code, []), profile,
                country_input.currency,
            )
        return out, collected

    @staticmethod
    def _subgroup_row(
        segment: DiseaseSubgroup,
        countries: Sequence[CountryRead],
        totals: TotalsRead,
    ) -> SubgroupResultRead:
        """One segment's line in the breakdown.

        Population and event counts sum across markets because they are counts.
        Net cost per switch is patient-weighted for the same reason it is in
        `segmentation` — a per-patient figure summed across markets is not a
        larger per-patient figure, it is a meaningless one.
        """
        final_patients = math.fsum(
            c.years[-1].patients_on_new for c in countries if c.years
        )
        weights = [c.years[-1].patients_on_new if c.years else 0.0 for c in countries]
        total_weight = math.fsum(weights)
        net_per_switch = (
            math.fsum(
                (c.years[-1].net_cost_per_switch if c.years else 0.0) * w
                for c, w in zip(countries, weights, strict=True)
            ) / total_weight
            if total_weight > 0 else 0.0
        )
        events = math.fsum(
            event.total_avoided
            for c in countries if c.outcomes
            for event in c.outcomes.events
        )
        cost_avoided = math.fsum(
            c.outcomes.total_cost_avoided for c in countries if c.outcomes
        )
        responders = [
            c.outcomes.responders_by_year[-1]
            for c in countries
            if c.outcomes and c.outcomes.responders_by_year
        ]

        return SubgroupResultRead(
            subgroup_code=segment.subgroup_code,
            subgroup_label=segment.subgroup_label,
            description=segment.description,
            share_of_diagnosed=float(segment.share_of_diagnosed),
            eligible_factor=float(segment.eligible_factor),
            uptake_multiplier=float(segment.uptake_multiplier),
            confidence_tier=str(segment.confidence_tier),
            source=segment.source,
            currency=totals.currency,
            by_year=list(totals.by_year),
            cumulative=totals.cumulative,
            peak_year=totals.peak_year,
            addressable_final_year=math.fsum(
                c.years[-1].addressable for c in countries if c.years
            ),
            patients_treated_final_year=final_patients,
            net_cost_per_switch=net_per_switch,
            total_events_avoided=events,
            total_cost_avoided=cost_avoided,
            responders_final_year=math.fsum(responders) if responders else None,
        )

    # ----------------------------------------------------------------- payer views

    def break_even(self, scenario: object) -> BreakEvenResponse:
        """M17 section 5.4 — the price at which impact is zero, per market."""
        engine_input, _ = self.build_input(scenario)
        entries, warnings = self._payer.break_even(engine_input)
        return BreakEvenResponse(
            scenario_id=engine_input.scenario_id,
            entries=entries,
            warnings=_warnings(warnings),
        )

    def uptake_scenarios(self, scenario: object) -> UptakeScenarioResponse:
        """M17 section 5.5 — low, medium and high adoption side by side."""
        segment = self._analysis_segment(scenario)

        def build(target: object, *, uptake_multiplier: float = 1.0):  # type: ignore[no-untyped-def]
            return self._builder.build(
                target, subgroup=segment,  # type: ignore[arg-type]
                uptake_multiplier=uptake_multiplier,
            )

        cases, warnings = self._payer.uptake_cases(build, scenario)
        base, _ = self.build_input(scenario)
        return UptakeScenarioResponse(
            scenario_id=base.scenario_id,
            currency=base.reporting_currency,
            cases=cases,
            warnings=_warnings(warnings),
        )

    def _country(
        self,
        cr: CountryResult,
        engine_input: EngineInput,
        affordability: object | None,
        outcomes: OutcomesRead | None = None,
    ) -> CountryRead:
        ci: CountryInput = next(
            c for c in engine_input.countries if c.country_code == cr.country_code
        )
        return CountryRead(
            country_code=cr.country_code,
            currency=cr.currency,
            cumulative_budget_impact=cr.cumulative_budget_impact.amount,
            funnel=[
                FunnelStageRead(
                    stage=str(s.stage), value=s.value, factor=s.factor,
                    provenance=_provenance(s.provenance),
                )
                for s in cr.funnel.stages
            ],
            years=[
                YearRead(
                    year=y.year, calendar_year=y.calendar_year, uptake=y.uptake,
                    addressable=y.addressable, patients_on_new=y.patients_on_new,
                    cost_without=y.cost_without.amount, cost_with=y.cost_with.amount,
                    budget_impact=y.budget_impact.amount,
                    net_cost_per_switch=y.net_cost_per_switch.amount,
                    impact_per_patient=(
                        y.impact_per_patient.amount if y.impact_per_patient else None
                    ),
                )
                for y in cr.years
            ],
            criteria=[
                CriterionRead(
                    code=c.code, label=c.label, factor=c.factor.value,
                    enabled=c.enabled, correlated_with=list(c.correlated_with),
                )
                for c in ci.criteria
            ],
            therapies=[_therapy(t, ci.currency) for t in ci.therapies],
            new_therapy=_therapy(ci.new_therapy, ci.currency),
            cost_bridge=_bridge(ci),
            outcomes=outcomes,
            affordability=(
                AffordabilityRead(
                    cumulative_ratio=affordability.cumulative_ratio,  # type: ignore[attr-defined]
                    band=str(affordability.band),                     # type: ignore[attr-defined]
                    health_budget=affordability.health_budget.amount,  # type: ignore[attr-defined]
                    pmpy=(
                        affordability.pmpy.amount                      # type: ignore[attr-defined]
                        if affordability.pmpy else None                # type: ignore[attr-defined]
                    ),
                )
                if affordability is not None else None
            ),
        )

    # ----------------------------------------------------------------- sensitivity

    def owsa(self, scenario: object) -> OwsaResponse:
        engine_input, _ = self.build_input(scenario)
        result = run_owsa(engine_input)
        return OwsaResponse(
            scenario_id=engine_input.scenario_id,
            base_result=result.base_result,
            currency=engine_input.reporting_currency,
            entries=[
                OwsaEntryRead(
                    parameter_path=e.parameter_path, label=e.label,
                    base_value=e.base_value, low_value=e.low_value,
                    high_value=e.high_value, result_at_low=e.result_at_low,
                    result_at_high=e.result_at_high, swing=e.swing, rank=e.rank,
                )
                for e in result.entries
            ],
            warnings=_warnings(result.warnings),
        )

    def psa(
        self,
        scenario: object,
        *,
        iterations: int = DEFAULT_PSA_ITERATIONS,
        seed: int = DEFAULT_PSA_SEED,
    ) -> PsaResponse:
        engine_input, _ = self.build_input(scenario)
        result = run_psa(engine_input, iterations=iterations, seed=seed)

        samples = list(result.samples)
        low, high = min(samples), max(samples)
        span = high - low
        bins = [0] * PSA_HISTOGRAM_BINS
        for sample in samples:
            # A zero span means every draw landed identically (no uncertainty
            # to sample); bucket 0 then holds them all rather than dividing
            # by zero.
            index = (
                0 if span == 0
                else min(int((sample - low) / span * PSA_HISTOGRAM_BINS), PSA_HISTOGRAM_BINS - 1)
            )
            bins[index] += 1

        return PsaResponse(
            scenario_id=engine_input.scenario_id,
            currency=engine_input.reporting_currency,
            iterations=result.iterations, seed=result.seed,
            mean=result.mean, median=result.median,
            p2_5=result.p2_5, p97_5=result.p97_5,
            histogram=bins, histogram_min=low, histogram_max=high,
            exceedance=dict(result.exceedance), converged=result.converged,
            warnings=_warnings(result.warnings),
        )

    # ----------------------------------------------------------------- persistence

    @staticmethod
    def snapshot(engine_input: EngineInput, response: CalculationResponse) -> dict[str, object]:
        """What gets frozen into `model_runs` — the resolved inputs and the
        results, so replaying through the recorded engine version reproduces
        this exact answer (M1 section 5.6)."""
        return {
            "input": engine_input.model_dump(mode="json"),
            "results": response.model_dump(mode="json"),
        }

    @staticmethod
    def run_type_forward() -> str:
        return RunType.FORWARD.value

    @staticmethod
    def engine_version() -> str:
        return engine_version


def new_run_id() -> uuid.UUID:
    return uuid.uuid4()
