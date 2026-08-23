"""Unit tests for biet_engine.eligibility — M3 section 10."""

from __future__ import annotations

import pytest

from biet_engine.eligibility import combine_criteria
from biet_engine.exceptions import CorrelatedCriteriaError
from biet_engine.models import ConfidenceTier

from ..conftest import make_criterion


def test_three_criteria_combine_multiplicatively() -> None:
    criteria = [
        make_criterion("bmi_ge_35", 0.55),
        make_criterion("age_18_75", 0.88),
        make_criterion("no_prior_glp1", 0.70),
    ]
    result = combine_criteria(criteria)
    assert result.combined_factor.value == pytest.approx(0.3388, abs=1e-4)


def test_golden_case_combined_factor() -> None:
    # The golden fixture (docs/modules/README.md) records only the pre-combined
    # criterion_stack value (0.350), not the individual criteria that produced
    # it — it's a frozen synthetic number, not a real criterion composition.
    # A single criterion whose factor is that value exercises the same
    # multiplication path without inventing a composition that was never
    # specified.
    criteria = [make_criterion("synthetic_stack", 0.350)]
    result = combine_criteria(criteria)
    assert result.combined_factor.value == pytest.approx(0.350, abs=1e-4)


def test_disabled_criteria_excluded_not_set_to_one() -> None:
    criteria = [
        make_criterion("bmi_ge_35", 0.55),
        make_criterion("age_18_75", 0.88, enabled=False),
    ]
    result = combine_criteria(criteria)
    assert result.combined_factor.value == pytest.approx(0.55)
    assert [c.code for c in result.applied] == ["bmi_ge_35"]


def test_empty_enabled_set_yields_one_with_synthetic_provenance() -> None:
    criteria = [make_criterion("bmi_ge_35", 0.55, enabled=False)]
    result = combine_criteria(criteria)
    assert result.combined_factor.value == 1.0
    assert result.combined_factor.provenance.source == "no criteria applied"
    assert result.combined_factor.provenance.confidence_tier == ConfidenceTier.C
    assert result.applied == ()


def test_no_criteria_at_all_yields_one() -> None:
    result = combine_criteria([])
    assert result.combined_factor.value == 1.0


def test_combined_tier_is_the_weakest_applied() -> None:
    criteria = [
        make_criterion("a", 0.5, tier=ConfidenceTier.A),
        make_criterion("b", 0.5, tier=ConfidenceTier.C),
    ]
    result = combine_criteria(criteria)
    assert result.combined_factor.provenance.confidence_tier == ConfidenceTier.C


def test_bounds_propagate_as_product_of_bounds() -> None:
    criteria = [
        make_criterion("a", 0.5, factor_low=0.4, factor_high=0.6),
        make_criterion("b", 0.8, factor_low=0.7, factor_high=0.9),
    ]
    result = combine_criteria(criteria)
    assert result.combined_factor.low == pytest.approx(0.4 * 0.7)
    assert result.combined_factor.high == pytest.approx(0.6 * 0.9)


def test_one_criterion_lacking_bounds_yields_none_bounds() -> None:
    criteria = [
        make_criterion("a", 0.5, factor_low=0.4, factor_high=0.6),
        make_criterion("b", 0.8),                # no bounds
    ]
    result = combine_criteria(criteria)
    assert result.combined_factor.low is None
    assert result.combined_factor.high is None


def test_factor_above_one_raises_value_error_at_construction() -> None:
    with pytest.raises(ValueError, match="factor"):
        make_criterion("bad", 1.15)


def test_correlated_pair_raises_in_strict_mode() -> None:
    criteria = [
        make_criterion("bmi_ge_35", 0.55, correlated_with=("cv_comorbidity",)),
        make_criterion("cv_comorbidity", 0.35, correlated_with=("bmi_ge_35",)),
    ]
    with pytest.raises(CorrelatedCriteriaError):
        combine_criteria(criteria, strict=True)


def test_correlated_pair_warns_and_proceeds_in_permissive_mode() -> None:
    criteria = [
        make_criterion("bmi_ge_35", 0.55, correlated_with=("cv_comorbidity",)),
        make_criterion("cv_comorbidity", 0.35, correlated_with=("bmi_ge_35",)),
    ]
    result = combine_criteria(criteria, strict=False)
    assert result.combined_factor.value == pytest.approx(0.55 * 0.35)
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "CORRELATED_CRITERIA"


def test_correlated_pair_not_both_enabled_does_not_raise() -> None:
    criteria = [
        make_criterion("bmi_ge_35", 0.55, correlated_with=("cv_comorbidity",)),
        make_criterion("cv_comorbidity", 0.35, enabled=False, correlated_with=("bmi_ge_35",)),
    ]
    result = combine_criteria(criteria, strict=True)
    assert result.combined_factor.value == pytest.approx(0.55)


def test_duplicate_criterion_codes_raise_value_error() -> None:
    criteria = [make_criterion("dup", 0.5), make_criterion("dup", 0.6)]
    with pytest.raises(ValueError, match="duplicate"):
        combine_criteria(criteria)
