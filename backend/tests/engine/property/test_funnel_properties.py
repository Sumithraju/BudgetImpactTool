"""Property tests for biet_engine.funnel — M2 section 10, "Property" class."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from biet_engine.funnel import compute_funnel

from ..conftest import make_country_input, make_valued

_RATE = st.floats(min_value=0.01, max_value=1.0, allow_nan=False)
_PREVALENCE = st.floats(min_value=0.001, max_value=0.999, allow_nan=False)
_POPULATION = st.floats(min_value=1.0, max_value=1e10, allow_nan=False)


@given(
    diagnosis_rate=_RATE, treatment_rate=_RATE, access_rate=_RATE,
    criteria_factor=_RATE, prevalence=_PREVALENCE,
)
def test_funnel_is_monotonically_non_increasing(
    diagnosis_rate: float, treatment_rate: float, access_rate: float,
    criteria_factor: float, prevalence: float,
) -> None:
    country = make_country_input(
        prevalence=prevalence, diagnosis_rate=diagnosis_rate,
        treatment_rate=treatment_rate, access_rate=access_rate,
    )
    result = compute_funnel(country, make_valued(criteria_factor), year=1)

    values = [stage.value for stage in result.stages]
    assert all(values[i] >= values[i + 1] for i in range(len(values) - 1))


@given(
    diagnosis_rate=_RATE, treatment_rate=_RATE, access_rate=_RATE,
    criteria_factor=_RATE, prevalence=_PREVALENCE,
)
def test_addressable_never_exceeds_total_population(
    diagnosis_rate: float, treatment_rate: float, access_rate: float,
    criteria_factor: float, prevalence: float,
) -> None:
    country = make_country_input(
        prevalence=prevalence, diagnosis_rate=diagnosis_rate,
        treatment_rate=treatment_rate, access_rate=access_rate,
    )
    result = compute_funnel(country, make_valued(criteria_factor), year=1)
    assert result.addressable <= result.stages[0].value


@given(population_total=_POPULATION, scale=st.floats(min_value=0.1, max_value=10.0))
def test_scaling_total_population_scales_every_stage(
    population_total: float, scale: float,
) -> None:
    base = make_country_input(population_total=population_total)
    scaled = make_country_input(population_total=population_total * scale)

    base_result = compute_funnel(base, make_valued(0.350), year=1)
    scaled_result = compute_funnel(scaled, make_valued(0.350), year=1)

    for base_stage, scaled_stage in zip(base_result.stages, scaled_result.stages):
        assert scaled_stage.value == pytest.approx(base_stage.value * scale, rel=1e-9)
