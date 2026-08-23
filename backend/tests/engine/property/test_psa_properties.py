"""Property tests for biet_engine.psa — M9 section 10, "Property" class."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from biet_engine.constants import PSA_DEFAULT_SEED
from biet_engine.models import Substitution, Valued
from biet_engine.psa import run_psa

from ..conftest import (
    make_country_input,
    make_engine_input,
    make_therapy_input,
    make_uptake_input,
    make_valued,
)


def _country_with_prevalence_interval(half_width: float):
    """A market whose prevalence carries an explicit published interval of
    the given half-width — the knob for 'wider input interval'."""
    new = make_therapy_input(drug_id=2, is_new=True, unit_price=300.0, currency="USD")
    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
    country = make_country_input(
        country_code="USA", currency="USD", horizon=1,
        therapies=(comparator,), new_therapy=new,
        baseline_shares={1: (1.0,)}, substitution=Substitution(shares={1: make_valued(1.0)}),
    )

    def _pin(v: Valued) -> Valued:
        return v.model_copy(update={"low": v.value, "high": v.value})

    base = country.prevalence.value
    return country.model_copy(update={
        # Everything except prevalence pinned, so the output spread is
        # attributable to the prevalence interval alone.
        "adult_share": _pin(country.adult_share),
        "prevalence": country.prevalence.model_copy(update={
            "low": max(1e-6, base - half_width), "high": min(0.999, base + half_width),
        }),
        "funnel": country.funnel.model_copy(update={
            "diagnosis_rate": _pin(country.funnel.diagnosis_rate),
            "treatment_rate": _pin(country.funnel.treatment_rate),
            "access_rate": _pin(country.funnel.access_rate),
        }),
        "criteria": tuple(
            c.model_copy(update={"factor": _pin(c.factor)}) for c in country.criteria
        ),
        "new_therapy": country.new_therapy.model_copy(update={
            "persistence_12m": _pin(country.new_therapy.persistence_12m),
        }),
        "therapies": tuple(
            t.model_copy(update={"persistence_12m": _pin(t.persistence_12m)})
            for t in country.therapies
        ),
    })


@given(iterations=st.integers(min_value=100, max_value=800),
       seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(deadline=None, max_examples=15)
def test_percentiles_are_ordered(iterations: int, seed: int) -> None:
    new = make_therapy_input(drug_id=2, is_new=True, unit_price=300.0, currency="USD")
    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
    country = make_country_input(
        country_code="USA", currency="USD", horizon=1,
        therapies=(comparator,), new_therapy=new,
        baseline_shares={1: (1.0,)}, substitution=Substitution(shares={1: make_valued(1.0)}),
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05,)),
    )
    result = run_psa(inputs, iterations=iterations, seed=seed)
    assert result.p2_5 <= result.median <= result.p97_5


def test_wider_input_interval_produces_a_wider_output_interval() -> None:
    def _spread(half_width: float) -> float:
        inputs = make_engine_input(
            countries=(_country_with_prevalence_interval(half_width),),
            horizon_years=1, reporting_currency="USD", fx_rates={"USD": 1.0},
            uptake=make_uptake_input(vector=(0.05,)),
        )
        result = run_psa(inputs, iterations=4_000, seed=PSA_DEFAULT_SEED)
        return result.p97_5 - result.p2_5

    narrow = _spread(0.01)
    wide = _spread(0.08)
    assert wide > narrow
