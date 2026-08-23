"""Construction-time validation on the shared engine models.

M2 section 6: "All factors in (0, 1] — Raise ValueError at construction."
`pydantic.ValidationError` subclasses `ValueError` in Pydantic v2, so
`pytest.raises(ValueError)` catches it correctly.
"""

from __future__ import annotations

import pytest

from biet_engine.constants import CriterionType
from biet_engine.models import Criterion, FunnelRates

from ..conftest import make_valued


def test_funnel_rates_rejects_diagnosis_rate_above_one() -> None:
    with pytest.raises(ValueError, match="diagnosis_rate"):
        FunnelRates(
            diagnosis_rate=make_valued(1.2),
            treatment_rate=make_valued(0.5),
            access_rate=make_valued(0.5),
        )


def test_funnel_rates_rejects_zero() -> None:
    with pytest.raises(ValueError, match="treatment_rate"):
        FunnelRates(
            diagnosis_rate=make_valued(0.5),
            treatment_rate=make_valued(0.0),
            access_rate=make_valued(0.5),
        )


def test_funnel_rates_accepts_one() -> None:
    rates = FunnelRates(
        diagnosis_rate=make_valued(1.0),
        treatment_rate=make_valued(0.5),
        access_rate=make_valued(0.5),
    )
    assert rates.diagnosis_rate.value == 1.0


def test_criterion_rejects_factor_above_one() -> None:
    with pytest.raises(ValueError, match="factor"):
        Criterion(
            code="test", label="test", type=CriterionType.BMI,
            factor=make_valued(1.5), enabled=True,
        )
