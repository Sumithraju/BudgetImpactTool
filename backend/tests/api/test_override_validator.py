"""Unit tests for override validation — M1 sections 5.1 and 6."""

from __future__ import annotations

import pytest

from biet_api.constants.parameter_paths import VALID_PATH_TEMPLATES, spec_for
from biet_api.exceptions import (
    ParameterOutOfRangeError,
    UnknownParameterPathError,
    ValidationError,
)
from biet_api.services.override_validator import validate_override

# --------------------------------------------------------------------------- vocabulary


@pytest.mark.parametrize("path", [
    "funnel.diagnosis_rate", "funnel.treatment_rate", "funnel.access_rate",
    "epidemiology.prevalence", "uptake.curve", "uptake.year_1", "uptake.terminal",
    "uptake.vector", "substitution.naive",
])
def test_literal_paths_are_recognised(path: str) -> None:
    assert spec_for(path) is not None


@pytest.mark.parametrize("path", [
    "criteria.bmi_ge_35.factor", "criteria.cv_comorbidity.enabled",
    "therapy.42.price_local", "therapy.7.persistence_12m",
    "therapy.7.market_share.2", "substitution.13",
])
def test_templated_paths_are_recognised(path: str) -> None:
    assert spec_for(path) is not None


@pytest.mark.parametrize("path", [
    "funnel.nonsense", "therapy.price_local", "therapy.abc.price_local",
    "criteria..factor", "", "substitution.", "uptake",
])
def test_paths_outside_the_vocabulary_are_rejected(path: str) -> None:
    assert spec_for(path) is None
    with pytest.raises(UnknownParameterPathError):
        validate_override(path, 0.5)


def test_unknown_path_error_lists_the_valid_paths() -> None:
    # Section 6 requires the 422 to name what *is* valid, not just what isn't.
    with pytest.raises(UnknownParameterPathError) as exc:
        validate_override("funnel.made_up", 0.5)
    assert exc.value.context["valid_paths"] == list(VALID_PATH_TEMPLATES)


# --------------------------------------------------------------------------- ranges


def test_rate_paths_reject_zero_but_accept_one() -> None:
    # A rate of 0 means the stage passes nobody — degenerate, not an
    # assumption. A rate of 1 (everybody) is legitimate.
    with pytest.raises(ParameterOutOfRangeError):
        validate_override("funnel.diagnosis_rate", 0.0)
    validate_override("funnel.diagnosis_rate", 1.0)


def test_rate_paths_reject_above_one() -> None:
    with pytest.raises(ParameterOutOfRangeError, match="at most"):
        validate_override("funnel.treatment_rate", 1.2)


def test_prevalence_is_open_at_both_ends() -> None:
    for bad in (0.0, 1.0):
        with pytest.raises(ParameterOutOfRangeError):
            validate_override("epidemiology.prevalence", bad)
    validate_override("epidemiology.prevalence", 0.2064)


def test_share_paths_accept_zero() -> None:
    # Zero uptake is a real scenario (M4 section 6), unlike a zero rate.
    validate_override("uptake.year_1", 0.0)
    validate_override("substitution.naive", 0.0)


def test_price_must_be_strictly_positive() -> None:
    with pytest.raises(ParameterOutOfRangeError, match="greater than"):
        validate_override("therapy.42.price_local", 0.0)
    validate_override("therapy.42.price_local", 1234.56)


def test_out_of_range_error_names_the_path() -> None:
    with pytest.raises(ParameterOutOfRangeError) as exc:
        validate_override("funnel.access_rate", 5.0)
    assert exc.value.context["parameter_path"] == "funnel.access_rate"


# --------------------------------------------------------------------------- types


def test_bool_path_requires_a_bool() -> None:
    validate_override("criteria.bmi_ge_35.enabled", True)
    with pytest.raises(ValidationError, match="boolean"):
        validate_override("criteria.bmi_ge_35.enabled", 1)


def test_float_path_rejects_a_bool() -> None:
    # bool subclasses int in Python, so True would sail through a naive
    # isinstance(value, (int, float)) check and be read as 1.0.
    with pytest.raises(ValidationError, match="number"):
        validate_override("funnel.diagnosis_rate", True)


def test_enum_path_accepts_only_declared_members() -> None:
    validate_override("uptake.curve", "logistic")
    with pytest.raises(ValidationError, match="one of"):
        validate_override("uptake.curve", "exponential")


def test_int_is_accepted_where_a_float_is_expected() -> None:
    validate_override("funnel.diagnosis_rate", 1)


# --------------------------------------------------------------------------- uptake.vector


def test_vector_length_must_equal_the_horizon() -> None:
    validate_override("uptake.vector", [0.05, 0.10, 0.15], horizon_years=3)
    with pytest.raises(ValidationError, match="one entry per year"):
        validate_override("uptake.vector", [0.05, 0.10], horizon_years=3)


def test_vector_length_unchecked_when_no_horizon_supplied() -> None:
    validate_override("uptake.vector", [0.05, 0.10])


def test_vector_elements_are_range_checked() -> None:
    with pytest.raises(ParameterOutOfRangeError, match=r"uptake\.vector\[1\]"):
        validate_override("uptake.vector", [0.05, 1.5], horizon_years=2)


def test_vector_rejects_a_non_sequence() -> None:
    with pytest.raises(ValidationError, match="list of numbers"):
        validate_override("uptake.vector", 0.05)


def test_vector_rejects_a_string() -> None:
    # A string is a Sequence, so it needs excluding explicitly.
    with pytest.raises(ValidationError, match="list of numbers"):
        validate_override("uptake.vector", "0.05,0.10")


def test_vector_rejects_non_numeric_elements() -> None:
    with pytest.raises(ValidationError, match=r"\[1\] expects a number"):
        validate_override("uptake.vector", [0.05, "0.10"], horizon_years=2)
