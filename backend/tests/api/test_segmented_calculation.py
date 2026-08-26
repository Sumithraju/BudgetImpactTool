"""Segmented calculation — M18 section 5.3 at the service layer.

The builder is stubbed: what is under test is the loop, the scaling and the
aggregation, not the resolution chain those already have tests for.
"""

from __future__ import annotations

import pytest

from biet_api.services.calculation_service import CalculationService, _scaled
from biet_engine.constants import Subgroup
from biet_engine.impact import compute_budget_impact
from biet_engine.models import Substitution

from ..engine.conftest import (
    make_country_input,
    make_criterion,
    make_engine_input,
    make_therapy_input,
    make_uptake_input,
    make_valued,
)

PREVALENCE = 0.2064


def golden_input():
    new_therapy = make_therapy_input(
        drug_id=2, is_new=True, unit_price=4800.0, currency="EUR", admins_per_year=1.0
    ).model_copy(update={"persistence_12m": make_valued(0.50)})
    comparator = make_therapy_input(
        drug_id=1, is_new=False, unit_price=1200.0, currency="EUR", admins_per_year=1.0
    ).model_copy(update={"persistence_12m": make_valued(0.70)})
    country = make_country_input(
        country_code="DEU", currency="EUR",
        population_total=83_500_000, adult_share=0.820, prevalence=PREVALENCE,
        diagnosis_rate=0.600, treatment_rate=0.150, access_rate=0.700,
        criteria=(make_criterion("synthetic_stack", 0.350),),
        horizon=3, therapies=(comparator,), new_therapy=new_therapy,
        baseline_shares={1: (1.0, 1.0, 1.0)},
        substitution=Substitution(shares={1: make_valued(1.0)}),
    )
    return make_engine_input(
        countries=(country,), horizon_years=3, reporting_currency="EUR",
        fx_rates={"EUR": 1.0, "USD": 0.86386},
        uptake=make_uptake_input(vector=(0.05, 0.12, 0.20)),
    )


class StubBuilder:
    def __init__(self, engine_input) -> None:
        self._input = engine_input

    def build(self, scenario, *, project_landscape: bool = False):
        return self._input, ()


@pytest.fixture
def service() -> CalculationService:
    svc = CalculationService.__new__(CalculationService)
    svc._builder = StubBuilder(golden_input())        # type: ignore[attr-defined]
    return svc


# ------------------------------------------------------------------ scaling


def test_scaling_prevalence_scales_only_prevalence() -> None:
    base = golden_input()
    scaled = _scaled(base, 0.25)
    original, segment = base.countries[0], scaled.countries[0]

    assert segment.prevalence.value == pytest.approx(original.prevalence.value * 0.25)
    assert segment.population_total == original.population_total
    assert segment.adult_share == original.adult_share
    assert segment.funnel == original.funnel


def test_scaling_carries_the_interval_with_the_value() -> None:
    """Dropping the bounds would silently widen the PSA on every segment."""
    base = golden_input()
    with_bounds = base.model_copy(update={
        "countries": (
            base.countries[0].model_copy(update={
                "prevalence": base.countries[0].prevalence.model_copy(
                    update={"low": 0.17, "high": 0.24}
                )
            }),
        )
    })
    segment = _scaled(with_bounds, 0.5).countries[0]
    assert segment.prevalence.low == pytest.approx(0.085)
    assert segment.prevalence.high == pytest.approx(0.12)


# -------------------------------------------------------------- the run


def test_the_segmented_total_reconciles_to_the_plain_run(service) -> None:
    """The acceptance criterion for M18: splitting a population into segments
    that carry identical inputs must reproduce the undifferentiated answer."""
    plain = compute_budget_impact(golden_input()).totals
    segmented = service.calculate_segments(object())

    assert segmented.totals.cumulative == pytest.approx(plain.cumulative.amount, rel=1e-9)
    assert segmented.totals.by_year == pytest.approx(
        [m.amount for m in plain.by_year], rel=1e-9
    )


def test_every_seeded_subgroup_appears_as_a_segment(service) -> None:
    segmented = service.calculate_segments(object())
    assert {s.code for s in segmented.segments} == {
        Subgroup.OBESITY_ESTABLISHED_CVD.value,
        Subgroup.OBESITY_T2D.value,
        Subgroup.OBESITY_HYPERTENSION.value,
        Subgroup.OBESITY_DYSLIPIDAEMIA.value,
        Subgroup.OBESITY_ALONE.value,
    }


def test_contributions_sum_to_the_whole(service) -> None:
    segmented = service.calculate_segments(object())
    assert sum(s.share_of_total_impact for s in segmented.segments) == pytest.approx(1.0)
    assert sum(s.cumulative_impact for s in segmented.segments) == pytest.approx(
        segmented.totals.cumulative, rel=1e-9
    )


def test_supplied_shares_override_the_seeded_ones(service) -> None:
    segmented = service.calculate_segments(
        object(), {Subgroup.OBESITY_T2D: 0.50}
    )
    by_code = {s.code: s for s in segmented.segments}
    assert by_code[Subgroup.OBESITY_T2D.value].share == pytest.approx(0.50)
    # Everything not supplied is zero, so the residual takes the rest.
    assert by_code[Subgroup.OBESITY_ALONE.value].share == pytest.approx(0.50)


def test_a_zero_share_segment_is_skipped_rather_than_run(service) -> None:
    """An empty funnel contributes nothing and would raise on its way there."""
    segmented = service.calculate_segments(
        object(), {Subgroup.OBESITY_T2D: 0.60, Subgroup.OBESITY_HYPERTENSION: 0.0}
    )
    assert Subgroup.OBESITY_HYPERTENSION.value not in {s.code for s in segmented.segments}


def test_moving_share_to_a_bigger_segment_moves_its_contribution(service) -> None:
    small = service.calculate_segments(object(), {Subgroup.OBESITY_T2D: 0.10})
    large = service.calculate_segments(object(), {Subgroup.OBESITY_T2D: 0.40})

    def t2d(response) -> float:
        return next(
            s.cumulative_impact for s in response.segments
            if s.code == Subgroup.OBESITY_T2D.value
        )

    assert t2d(large) > t2d(small)
    # And the scenario total does not move: the share came out of the residual.
    assert large.totals.cumulative == pytest.approx(small.totals.cumulative, rel=1e-9)


def test_the_two_worlds_survive_segmentation(service) -> None:
    segmented = service.calculate_segments(object())
    for year in range(segmented.horizon_years):
        assert (
            segmented.totals.with_by_year[year] - segmented.totals.without_by_year[year]
        ) == pytest.approx(segmented.totals.by_year[year], rel=1e-9)
