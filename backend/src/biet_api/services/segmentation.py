"""Aggregating segmented runs — M18's other half.

M18's design point is that a subgroup is a *scenario dimension*: the engine
runs unchanged once per segment and the results aggregate. `engine_input.py`
implements the first half by turning a segment into two criteria and an uptake
multiplier. This module implements the second — putting the pieces back
together into one result a reader can hold.

The aggregation is not a uniform sum, and the reason is the funnel. Segments
partition the *diagnosed* population, so every stage from total population down
to treated is **identical** in every segment — summing them across six segments
would report six times the country's population. Only the stages below the
criterion stack, where the segment factor bites, actually differ and sum. That
split is the whole content of this module, and getting it wrong is not subtle:
it would sextuple the top of the funnel and leave the bottom right, which is
exactly the kind of error that survives review because the number a reader
checks first is still correct.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from biet_engine.affordability import band_for
from biet_engine.constants import FunnelStage

from ..schemas.calculation import (
    AffordabilityRead,
    BridgeTermRead,
    CostBridgeRead,
    CountryRead,
    CriterionRead,
    FunnelStageRead,
    OutcomesRead,
    TotalsRead,
    YearRead,
)

#: Funnel stages that differ between segments and therefore sum across them.
#: Every stage above these is a property of the market, not of the segment.
#: Derived from `FunnelStage`'s declared order rather than listed by hand, so
#: adding a stage to the funnel cannot silently leave this behind.
_STAGE_ORDER: tuple[FunnelStage, ...] = tuple(FunnelStage)
_FIRST_SEGMENTED_STAGE = FunnelStage.LABEL_ELIGIBLE
SEGMENTED_STAGES: frozenset[str] = frozenset(
    stage.value
    for stage in _STAGE_ORDER[_STAGE_ORDER.index(_FIRST_SEGMENTED_STAGE):]
)

#: Criterion codes this system generates for a segment. Stripped from the
#: aggregate's criterion list, because a stack showing "Segment — obesity with
#: diabetes: x0.19" alongside five other segments' factors describes no single
#: population. The per-segment panel carries them instead.
SEGMENT_CODE_PREFIX = "segment_"


def _weighted(values: Sequence[float], weights: Sequence[float]) -> float:
    """A patient-weighted mean, falling back to a plain mean with no patients.

    Per-patient figures — net cost per switch, every bridge term — cannot be
    summed across segments. Weighting them by patients treated is the only
    aggregation that reproduces the total when multiplied back out. With no
    patients anywhere the weights are meaningless and an unweighted mean at
    least reports the right order of magnitude rather than zero.
    """
    total_weight = math.fsum(weights)
    if total_weight <= 0:
        return math.fsum(values) / len(values) if values else 0.0
    return math.fsum(v * w for v, w in zip(values, weights, strict=True)) / total_weight


def aggregate_countries(
    per_segment: Sequence[Sequence[CountryRead]],
) -> list[CountryRead]:
    """One country result per market, summed across segments.

    `per_segment[s][c]` is segment `s`'s result for market `c`; every segment
    runs the same market list in the same order, because they are built from
    one scenario.
    """
    if not per_segment:
        return []
    if len(per_segment) == 1:
        return list(per_segment[0])

    aggregated: list[CountryRead] = []
    for index in range(len(per_segment[0])):
        segments = [segment[index] for segment in per_segment]
        aggregated.append(_aggregate_country(segments))
    return aggregated


def _aggregate_country(segments: Sequence[CountryRead]) -> CountryRead:
    first = segments[0]
    horizon = len(first.years)
    patients = [
        math.fsum(s.years[y].patients_on_new for s in segments) for y in range(horizon)
    ]

    years = [
        YearRead(
            year=first.years[y].year,
            calendar_year=first.years[y].calendar_year,
            # Uptake is a *share* of each segment's own addressable population,
            # so the aggregate is the share of the combined addressable
            # population — patients over addressable, not a mean of shares.
            uptake=(
                math.fsum(s.years[y].patients_on_new for s in segments)
                / math.fsum(s.years[y].addressable for s in segments)
                if math.fsum(s.years[y].addressable for s in segments) > 0 else 0.0
            ),
            addressable=math.fsum(s.years[y].addressable for s in segments),
            patients_on_new=patients[y],
            cost_without=math.fsum(s.years[y].cost_without for s in segments),
            cost_with=math.fsum(s.years[y].cost_with for s in segments),
            budget_impact=math.fsum(s.years[y].budget_impact for s in segments),
            net_cost_per_switch=_weighted(
                [s.years[y].net_cost_per_switch for s in segments],
                [s.years[y].patients_on_new for s in segments],
            ),
            impact_per_patient=_weighted(
                [s.years[y].impact_per_patient or 0.0 for s in segments],
                [s.years[y].patients_on_new for s in segments],
            ),
        )
        for y in range(horizon)
    ]

    cumulative = math.fsum(s.cumulative_budget_impact for s in segments)

    return CountryRead(
        country_code=first.country_code,
        currency=first.currency,
        cumulative_budget_impact=cumulative,
        funnel=_aggregate_funnel(segments),
        years=years,
        criteria=[
            c for c in first.criteria if not c.code.startswith(SEGMENT_CODE_PREFIX)
        ],
        therapies=first.therapies,
        new_therapy=first.new_therapy,
        affordability=_aggregate_affordability(segments, cumulative),
        cost_bridge=_aggregate_bridge(segments),
        outcomes=_aggregate_outcomes(segments),
        payer=None,        # recomputed by the caller from the aggregate
    )


def _aggregate_funnel(segments: Sequence[CountryRead]) -> list[FunnelStageRead]:
    """Shared stages taken once; segmented stages summed.

    See the module docstring for why this is not a uniform sum. The `factor`
    on a segmented stage is recomputed as the ratio to the stage above rather
    than carried through, because each segment applied a different one and no
    single factor produced the aggregate.
    """
    first = segments[0]
    out: list[FunnelStageRead] = []
    for position, stage in enumerate(first.funnel):
        if stage.stage not in SEGMENTED_STAGES:
            out.append(stage)
            continue

        value = math.fsum(s.funnel[position].value for s in segments)
        previous = out[position - 1].value if position > 0 else 0.0
        out.append(FunnelStageRead(
            stage=stage.stage,
            value=value,
            factor=(value / previous) if previous > 0 else None,
            provenance=stage.provenance,
        ))
    return out


def _aggregate_affordability(
    segments: Sequence[CountryRead], cumulative: float,
) -> AffordabilityRead | None:
    """The ratio recomputed against the market's own health budget.

    The budget is a property of the country and is identical in every segment,
    so it is taken once and the ratio recomputed — summing six ratios against
    the same denominator would multiply the answer by six.

    The band is reclassified against that recomputed ratio, using the engine's
    own `band_for` rather than a copy of the thresholds. Carrying a segment's
    band through unchanged would be worse than wrong: each segment was
    classified on a fraction of the total impact, so a run whose combined
    impact is critical would report itself as low on the strength of its
    smallest segment.
    """
    first = segments[0]
    if first.affordability is None:
        return None
    budget = first.affordability.health_budget
    ratio = (cumulative / budget) if budget > 0 else 0.0
    return AffordabilityRead(
        cumulative_ratio=ratio,
        band=str(band_for(ratio)),
        health_budget=budget,
        pmpy=None,
    )


def _aggregate_bridge(segments: Sequence[CountryRead]) -> CostBridgeRead | None:
    """The bridge, patient-weighted across segments.

    Every term is a per-patient figure, so the weighted mean is the only
    aggregation under which the terms still sum to the aggregate net cost per
    switch — which is the one property the bridge exists to have.
    """
    bridges = [s.cost_bridge for s in segments if s.cost_bridge is not None]
    if not bridges:
        return None

    weights = [
        math.fsum(y.patients_on_new for y in s.years)
        for s in segments if s.cost_bridge is not None
    ]
    components = [term.component for term in bridges[0].terms]
    terms = [
        BridgeTermRead(
            component=component,
            new_therapy=_weighted(
                [b.terms[i].new_therapy for b in bridges], weights,
            ),
            displaced=_weighted([b.terms[i].displaced for b in bridges], weights),
            delta=_weighted([b.terms[i].delta for b in bridges], weights),
        )
        for i, component in enumerate(components)
    ]
    return CostBridgeRead(
        terms=terms,
        net_cost_per_switch=_weighted(
            [b.net_cost_per_switch for b in bridges], weights,
        ),
    )


def _aggregate_outcomes(segments: Sequence[CountryRead]) -> OutcomesRead | None:
    """Events and responders summed; the response profile taken once.

    Avoided events are counts and sum straight across segments — the whole
    reason segments exist is that the same relative reduction produces
    different counts in each. Mean weight loss is a property of the therapy and
    is identical everywhere, so it is taken rather than averaged.
    """
    present = [s.outcomes for s in segments if s.outcomes is not None]
    if not present:
        return None

    first = present[0]
    horizon = len(first.total_cost_avoided_by_year)

    by_event: dict[str, list[object]] = {}
    for outcome in present:
        for event in outcome.events:
            by_event.setdefault(event.event_class, []).append(event)

    events = []
    for rows in by_event.values():
        head = rows[0]
        events.append(head.model_copy(update={  # type: ignore[attr-defined]
            "events_without_by_year": [
                math.fsum(r.events_without_by_year[y] for r in rows)  # type: ignore[attr-defined]
                for y in range(horizon)
            ],
            "avoided_by_year": [
                math.fsum(r.avoided_by_year[y] for r in rows)  # type: ignore[attr-defined]
                for y in range(horizon)
            ],
            "cost_avoided_by_year": [
                math.fsum(r.cost_avoided_by_year[y] for r in rows)  # type: ignore[attr-defined]
                for y in range(horizon)
            ],
            "total_avoided": math.fsum(r.total_avoided for r in rows),  # type: ignore[attr-defined]
            "total_cost_avoided": math.fsum(
                r.total_cost_avoided for r in rows  # type: ignore[attr-defined]
            ),
            # The baseline rate differs by segment, so the aggregate carries
            # the patient-weighted one rather than any single segment's — and
            # the per-segment panel keeps each of them visible.
            "baseline_annual_rate": _weighted(
                [r.baseline_annual_rate for r in rows],  # type: ignore[attr-defined]
                [math.fsum(r.avoided_by_year) or 1.0 for r in rows],  # type: ignore[attr-defined]
            ),
        }))

    responders = None
    if any(o.responders_by_year for o in present):
        responders = [
            math.fsum(
                (o.responders_by_year or [0.0] * horizon)[y] for o in present
            )
            for y in range(horizon)
        ]

    seen: set[str] = set()
    warnings = []
    for outcome in present:
        for warning in outcome.warnings:
            key = f"{warning.code}:{warning.message}"
            if key not in seen:
                seen.add(key)
                warnings.append(warning)

    return OutcomesRead(
        country_code=first.country_code,
        currency=first.currency,
        responders_by_year=responders,
        mean_weight_loss_pct=first.mean_weight_loss_pct,
        responder_threshold=first.responder_threshold,
        responder_trial=first.responder_trial,
        regain_per_year=first.regain_per_year,
        events=sorted(events, key=lambda e: -e.total_cost_avoided),
        total_cost_avoided=math.fsum(o.total_cost_avoided for o in present),
        total_cost_avoided_by_year=[
            math.fsum(o.total_cost_avoided_by_year[y] for o in present)
            for y in range(horizon)
        ],
        warnings=warnings,
    )


def aggregate_totals(totals: Sequence[TotalsRead]) -> TotalsRead:
    """Cross-segment totals in the reporting currency.

    Peak year is recomputed from the summed series rather than taken from any
    segment: segments peak in different years when their uptake multipliers
    differ, and the peak of the sum is not the sum of the peaks.
    """
    if len(totals) == 1:
        return totals[0]

    horizon = len(totals[0].by_year)
    by_year = [math.fsum(t.by_year[y] for t in totals) for y in range(horizon)]
    return TotalsRead(
        by_year=by_year,
        cumulative=math.fsum(t.cumulative for t in totals),
        # Ties resolve to the earliest year, matching M7's own convention.
        peak_year=(by_year.index(max(by_year)) + 1) if by_year else 1,
        currency=totals[0].currency,
    )


def strip_segment_criteria(criteria: Sequence[CriterionRead]) -> list[CriterionRead]:
    return [c for c in criteria if not c.code.startswith(SEGMENT_CODE_PREFIX)]
