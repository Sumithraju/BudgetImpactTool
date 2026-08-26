"""Runs the engine and maps its output to the HTTP contract.

The engine is called here and nowhere else in the API. It receives a fully
resolved `EngineInput` and returns frozen results; this module's only job is
to invoke it, persist the run, and translate the result into response
schemas. No calculation happens in this file.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from biet_engine import __version__ as engine_version
from biet_engine.affordability import compute_affordability
from biet_engine.constants import (
    SUBGROUP_PRIORITY,
    SUPPLIED_SUBGROUPS,
    ConfidenceTier,
    ResolutionLevel,
    Subgroup,
)
from biet_engine.cost import compute_therapy_cost
from biet_engine.impact import compute_budget_impact
from biet_engine.models import (
    CountryInput,
    CountryResult,
    EngineInput,
    EngineResult,
    Provenance,
    SubgroupShare,
    TherapyInput,
    Valued,
    Warning_,
)
from biet_engine.persistence import persistence_fraction
from biet_engine.psa import run_psa
from biet_engine.safety import build_cost_bridge
from biet_engine.sensitivity import run_owsa
from biet_engine.subgroups import aggregate_segments, allocate_shares

from ..constants.domain import RunType
from ..constants.subgroups import DEFAULT_SUBGROUP_SHARES, SUBGROUP_LABELS
from ..schemas.calculation import (
    AffordabilityRead,
    BridgeTermRead,
    CalculationResponse,
    CostBridgeRead,
    CountryRead,
    CriterionRead,
    FunnelStageRead,
    OwsaEntryRead,
    OwsaResponse,
    ProvenanceRead,
    PsaResponse,
    SegmentedCalculationResponse,
    SegmentRead,
    TherapyRead,
    TotalsRead,
    WarningRead,
    YearRead,
)
from .engine_input import EngineInputBuilder

#: Buckets for the PSA histogram. Enough shape to read the skew, few enough
#: that the payload stays small — the interface never plots raw samples.
PSA_HISTOGRAM_BINS = 36

#: Provenance for a share arriving from the interface rather than the seed.
_SEGMENT_PROVENANCE = Provenance(
    source="scenario subgroup split",
    confidence_tier=ConfidenceTier.C,
    resolution_level=ResolutionLevel.SCENARIO_OVERRIDE,
)


def _scaled(base: EngineInput, share: float) -> EngineInput:
    """The same scenario, restricted to one subgroup's slice of the disease.

    Scaling prevalence is the whole mechanism: `diseased = population x adult
    share x prevalence`, so multiplying prevalence by the segment's share
    yields exactly that segment's diseased count and leaves every rate beneath
    it — diagnosis, treatment, eligibility, access — free to differ per
    segment later without touching the engine.
    """
    return base.model_copy(update={
        "countries": tuple(
            country.model_copy(update={
                "prevalence": country.prevalence.model_copy(update={
                    "value": country.prevalence.value * share,
                    "low": None if country.prevalence.low is None
                           else country.prevalence.low * share,
                    "high": None if country.prevalence.high is None
                            else country.prevalence.high * share,
                })
            })
            for country in base.countries
        )
    })


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


class CalculationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._builder = EngineInputBuilder(session)

    def build_input(self, scenario: object) -> tuple[EngineInput, tuple[Warning_, ...]]:
        """Resolve a scenario without calculating — for callers like the
        solver that drive the engine themselves."""
        return self._builder.build(scenario)  # type: ignore[arg-type]

    # ----------------------------------------------------------------- forward

    def calculate(
        self, scenario: object, *, project_landscape: bool = False,
    ) -> tuple[CalculationResponse, EngineInput, EngineResult]:
        """Forward run: funnel through incremental budget impact.

        `project_landscape` admits M14's pipeline entrants into the
        world-without. Off by default and never implicit: it changes what the
        new asset is compared against, on assumptions the evidence does not
        supply.

        Returns the response alongside the raw engine input and result, so a
        caller that also wants sensitivity does not rebuild and recompute.
        """
        started = time.perf_counter()
        engine_input, resolution_warnings = self._builder.build(
            scenario, project_landscape=project_landscape,  # type: ignore[arg-type]
        )
        result = compute_budget_impact(engine_input)
        affordability = compute_affordability(result, engine_input)
        duration_ms = int((time.perf_counter() - started) * 1000)

        by_code = {a.country_code: a for a in affordability}
        countries = [
            self._country(cr, engine_input, by_code.get(cr.country_code))
            for cr in result.countries
        ]

        response = CalculationResponse(
            scenario_id=engine_input.scenario_id,
            engine_version=result.engine_version,
            reporting_currency=result.reporting_currency,
            fx_snapshot_date=result.fx_snapshot_date,
            launch_year=engine_input.launch_year,
            horizon_years=engine_input.horizon_years,
            countries=countries,
            totals=TotalsRead(
                by_year=[m.amount for m in result.totals.by_year],
                cumulative=result.totals.cumulative.amount,
                peak_year=result.totals.peak_year,
                currency=result.totals.cumulative.currency,
                without_by_year=[m.amount for m in result.totals.without_by_year],
                with_by_year=[m.amount for m in result.totals.with_by_year],
            ),
            warnings=_warnings(list(resolution_warnings) + list(result.warnings)),
            duration_ms=duration_ms,
        )
        return response, engine_input, result

    def calculate_segments(
        self,
        scenario: object,
        shares: dict[Subgroup, float] | None = None,
        *,
        project_landscape: bool = False,
    ) -> SegmentedCalculationResponse:
        """Run the scenario once per subgroup and aggregate — M18 section 5.3.

        The engine is called unchanged, once per segment. A subgroup is a
        *scenario dimension*: scaling a market's prevalence by the segment's
        share scales the `diseased` stage and nothing else, which is exactly
        what a subgroup is — a slice of the people who have the disease,
        running through the same funnel beneath it. That is what lets
        `biet_engine` stay pure and keeps `compute_budget_impact`'s signature
        untouched.

        A segment with a zero share is skipped rather than run: it would
        contribute nothing and its empty funnel would raise on its way there.
        """
        started = time.perf_counter()
        supplied = shares or dict(DEFAULT_SUBGROUP_SHARES)
        allocation, allocation_warnings = allocate_shares([
            SubgroupShare(
                subgroup=subgroup,
                share=Valued(value=share, provenance=_SEGMENT_PROVENANCE),
            )
            for subgroup, share in supplied.items()
            if subgroup in SUPPLIED_SUBGROUPS
        ])

        base, resolution_warnings = self._builder.build(
            scenario, project_landscape=project_landscape,  # type: ignore[arg-type]
        )

        runs = []
        for subgroup in SUBGROUP_PRIORITY:
            share = allocation[subgroup]
            if share <= 0.0:
                continue
            runs.append((subgroup, share, compute_budget_impact(_scaled(base, share))))

        aggregate = aggregate_segments(runs)
        duration_ms = int((time.perf_counter() - started) * 1000)

        return SegmentedCalculationResponse(
            scenario_id=base.scenario_id,
            engine_version=engine_version,
            reporting_currency=base.reporting_currency,
            launch_year=base.launch_year,
            horizon_years=base.horizon_years,
            totals=TotalsRead(
                by_year=[m.amount for m in aggregate.totals.by_year],
                cumulative=aggregate.totals.cumulative.amount,
                peak_year=aggregate.totals.peak_year,
                currency=aggregate.totals.cumulative.currency,
                without_by_year=[m.amount for m in aggregate.totals.without_by_year],
                with_by_year=[m.amount for m in aggregate.totals.with_by_year],
            ),
            segments=[
                SegmentRead(
                    code=c.subgroup.value,
                    label=SUBGROUP_LABELS[c.subgroup],
                    share=c.share,
                    cumulative_impact=c.cumulative_impact.amount,
                    share_of_total_impact=c.share_of_total_impact,
                    addressable_final_year=c.addressable_final_year,
                    patients_on_new_final_year=c.patients_on_new_final_year,
                )
                for c in aggregate.contributions
            ],
            warnings=_warnings(
                list(resolution_warnings)
                + list(allocation_warnings)
                + list(aggregate.warnings)
            ),
            duration_ms=duration_ms,
        )

    def _country(
        self,
        cr: CountryResult,
        engine_input: EngineInput,
        affordability: object | None,
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
        engine_input, _ = self._builder.build(scenario)  # type: ignore[arg-type]
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
        engine_input, _ = self._builder.build(scenario)  # type: ignore[arg-type]
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
