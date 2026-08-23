"""Eligibility & Segmentation — ARCHITECTURE.md module M3.

Combines a criterion stack into the single multiplicative factor M2 applies
at the `label_eligible` stage. Depends on nothing but the criteria passed in;
the criterion library itself, scenario overrides and correlation resolution
happen upstream (M0/M1).
"""

from __future__ import annotations

from collections.abc import Sequence

from .exceptions import CorrelatedCriteriaError
from .models import (
    ConfidenceTier,
    CriteriaResult,
    Criterion,
    Provenance,
    ResolutionLevel,
    Valued,
    Warning_,
)

#: Provenance for the empty-enabled-set case (M3 section 5.1) — synthetic,
#: not resolved from any source, so tier C rather than claiming a stronger one.
_NO_CRITERIA_PROVENANCE = Provenance(
    source="no criteria applied",
    confidence_tier=ConfidenceTier.C,
    resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
)


def combine_criteria(criteria: Sequence[Criterion], *, strict: bool = True) -> CriteriaResult:
    """Combine enabled criteria into one multiplicative eligibility factor.

        combined_factor = product over enabled k of factor(k)

    Disabled criteria are excluded, not set to 1.0, so `CriteriaResult.applied`
    is an accurate record of what was actually applied. An empty enabled set
    yields `combined_factor = 1.0` with synthetic tier-C provenance.

    Bounds propagate as the product of bounds only when every applied
    criterion carries them; otherwise the combined result has `low = high =
    None` rather than a fabricated interval (section 5.2).

    The combined confidence tier is the weakest among applied criteria — a
    chain is no stronger than its weakest link (section 5.3).

    Args:
        criteria: the full criterion set for this scenario, enabled and
            disabled alike.
        strict: when True (the default, used by API calls), two enabled
            criteria that declare each other in `correlated_with` raise
            `CorrelatedCriteriaError`. When False (M9's sensitivity sweeps,
            where blocking would abort the analysis), the same condition
            instead adds a `CORRELATED_CRITERIA` warning to the result and
            proceeds.

    Returns:
        The combined factor, the criteria actually applied (enabled only, in
        the order given), and any non-fatal warnings.

    Raises:
        ValueError: two criteria share the same `code`.
        CorrelatedCriteriaError: a correlated pair is both enabled, in strict
            mode.
    """
    codes = [c.code for c in criteria]
    if len(codes) != len(set(codes)):
        duplicates = {code for code in codes if codes.count(code) > 1}
        raise ValueError(f"duplicate criterion code(s): {sorted(duplicates)}")

    applied = tuple(c for c in criteria if c.enabled)
    warnings: list[Warning_] = []

    for pair in _correlated_pairs(applied):
        if strict:
            raise CorrelatedCriteriaError(
                f"{pair[0].code!r} and {pair[1].code!r} are correlated and "
                "both enabled",
                codes=(pair[0].code, pair[1].code),
            )
        warnings.append(
            Warning_(
                code="CORRELATED_CRITERIA",
                message=f"{pair[0].code!r} and {pair[1].code!r} are correlated "
                        "and both enabled; their marginal factors were "
                        "multiplied anyway (permissive mode)",
            )
        )

    if not applied:
        return CriteriaResult(
            combined_factor=Valued(value=1.0, provenance=_NO_CRITERIA_PROVENANCE),
            applied=(),
            warnings=tuple(warnings),
        )

    combined_value = 1.0
    for criterion in applied:
        combined_value *= criterion.factor.value

    bounds = [c.factor.low for c in applied]
    combined_low = _product(bounds) if all(b is not None for b in bounds) else None
    bounds_high = [c.factor.high for c in applied]
    combined_high = _product(bounds_high) if all(b is not None for b in bounds_high) else None

    combined_tier = max(c.factor.provenance.confidence_tier for c in applied)

    return CriteriaResult(
        combined_factor=Valued(
            value=combined_value,
            low=combined_low,
            high=combined_high,
            provenance=Provenance(
                source="combined: " + ", ".join(c.code for c in applied),
                confidence_tier=combined_tier,
                resolution_level=ResolutionLevel.SCENARIO_OVERRIDE,
            ),
        ),
        applied=applied,
        warnings=tuple(warnings),
    )


def _correlated_pairs(applied: Sequence[Criterion]) -> list[tuple[Criterion, Criterion]]:
    """Enabled pairs where either side declares the other in `correlated_with`."""
    pairs: list[tuple[Criterion, Criterion]] = []
    for i, a in enumerate(applied):
        for b in applied[i + 1:]:
            if b.code in a.correlated_with or a.code in b.correlated_with:
                pairs.append((a, b))
    return pairs


def _product(values: Sequence[float | None]) -> float:
    result = 1.0
    for v in values:
        assert v is not None                # narrowed by the caller's all(...) check
        result *= v
    return result
