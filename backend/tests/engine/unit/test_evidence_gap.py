"""Unit tests for biet_engine.evidence_gap — M15 section 10."""

from __future__ import annotations

import pytest

from biet_engine.constants import (
    EVIDENCE_PRIORITY_THRESHOLDS,
    TIER_WEAKNESS,
    ConfidenceTier,
    EvidencePriority,
    ResolutionLevel,
)
from biet_engine.evidence_gap import rank_evidence_gaps
from biet_engine.models import OwsaEntry, Provenance


def _entry(path: str, swing: float, rank: int = 1) -> OwsaEntry:
    return OwsaEntry(
        parameter_path=path, label=path.replace(".", " "), base_value=0.5,
        low_value=0.4, high_value=0.6, result_at_low=0.0, result_at_high=swing,
        swing=swing, rank=rank,
    )


def _prov(tier: ConfidenceTier, source: str = "a source") -> Provenance:
    return Provenance(
        source=source, confidence_tier=tier,
        resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
    )


def _rank(entries, provenance):
    return rank_evidence_gaps(entries, provenance, currency="USD")


# --------------------------------------------------------------------------- weights


def test_weights_and_bands_match_the_specification() -> None:
    assert TIER_WEAKNESS == {
        ConfidenceTier.A: 0.05, ConfidenceTier.B: 0.25,
        ConfidenceTier.C: 0.60, ConfidenceTier.D: 1.00,
    }
    assert EVIDENCE_PRIORITY_THRESHOLDS == {
        EvidencePriority.CRITICAL: 0.50,
        EvidencePriority.HIGH: 0.25,
        EvidencePriority.MEDIUM: 0.10,
    }


def test_tier_a_is_not_zero_weighted() -> None:
    """A published country-specific figure can still be the thing most worth
    re-checking if it dominates the tornado, and a weight of zero would make
    that impossible to see."""
    assert TIER_WEAKNESS[ConfidenceTier.A] > 0


# --------------------------------------------------------------------------- ranking


def test_a_weak_source_outranks_a_strong_one_at_the_same_swing() -> None:
    """The whole point. Two parameters move the answer identically; only one
    of them is worth a week of research."""
    report = _rank(
        [_entry("weak", 1000.0), _entry("strong", 1000.0)],
        {"weak": _prov(ConfidenceTier.D), "strong": _prov(ConfidenceTier.A)},
    )
    assert [g.parameter_path for g in report.gaps] == ["weak", "strong"]


def test_a_high_swing_tier_a_can_rank_below_a_lower_swing_tier_d() -> None:
    """The tornado would have put the tier-A parameter first. That is the
    ranking this module exists to correct."""
    report = _rank(
        [_entry("published", 1000.0), _entry("placeholder", 400.0)],
        {"published": _prov(ConfidenceTier.A), "placeholder": _prov(ConfidenceTier.D)},
    )
    assert report.gaps[0].parameter_path == "placeholder"


def test_a_zero_swing_parameter_is_never_a_priority() -> None:
    """Time spent pinning down a value that cannot move the result is time
    not spent on the one that can."""
    report = _rank(
        [_entry("mover", 1000.0), _entry("inert", 0.0)],
        {"mover": _prov(ConfidenceTier.B), "inert": _prov(ConfidenceTier.D)},
    )
    inert = next(g for g in report.gaps if g.parameter_path == "inert")
    assert inert.priority_score == 0.0
    assert inert.priority is EvidencePriority.SUFFICIENT


def test_all_zero_swings_do_not_divide_by_zero() -> None:
    """A scenario where nothing moves the answer is a real state, and must
    not crash on the way to saying so."""
    report = _rank(
        [_entry("a", 0.0), _entry("b", 0.0)],
        {"a": _prov(ConfidenceTier.D), "b": _prov(ConfidenceTier.D)},
    )
    assert all(g.influence == 0.0 for g in report.gaps)
    assert all(g.priority is EvidencePriority.SUFFICIENT for g in report.gaps)


def test_an_empty_sensitivity_gives_an_empty_report() -> None:
    report = _rank([], {})
    assert report.gaps == ()
    assert report.max_swing.amount == 0.0


def test_the_top_parameter_has_influence_of_exactly_one() -> None:
    """Normalising by the maximum swing makes the ranking scale-free across
    scenarios, at the cost of this. The output is an ordering, not a
    magnitude, so that is an acceptable trade."""
    report = _rank(
        [_entry("big", 800.0), _entry("small", 200.0)],
        {"big": _prov(ConfidenceTier.C), "small": _prov(ConfidenceTier.C)},
    )
    top = max(report.gaps, key=lambda g: g.swing.amount)
    assert top.influence == pytest.approx(1.0)


# --------------------------------------------------------------------------- provenance


def test_a_parameter_with_no_provenance_is_treated_as_tier_d_and_flagged() -> None:
    """An unattributed value is a placeholder by definition, whatever number
    is in it — but an *admitted* placeholder and an unattributed one are not
    the same problem, so the flag distinguishes them."""
    report = _rank([_entry("orphan", 1000.0)], {})
    gap = report.gaps[0]
    assert gap.confidence_tier is ConfidenceTier.D
    assert gap.has_provenance is False
    assert "no stated source" in gap.source


def test_every_gap_states_what_the_value_rests_on() -> None:
    report = _rank(
        [_entry("p", 500.0)], {"p": _prov(ConfidenceTier.B, "WHO GHO NCD_BMI_30A")},
    )
    assert report.gaps[0].source == "WHO GHO NCD_BMI_30A"


# --------------------------------------------------------------------------- bands & order


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        (ConfidenceTier.D, EvidencePriority.CRITICAL),   # 1.00 x 1.00
        (ConfidenceTier.C, EvidencePriority.CRITICAL),   # 1.00 x 0.60
        (ConfidenceTier.B, EvidencePriority.HIGH),       # 1.00 x 0.25
        (ConfidenceTier.A, EvidencePriority.SUFFICIENT),  # 1.00 x 0.05
    ],
)
def test_bands_at_full_influence(tier: ConfidenceTier, expected: EvidencePriority) -> None:
    report = _rank([_entry("p", 1000.0)], {"p": _prov(tier)})
    assert report.gaps[0].priority is expected


def test_ties_break_deterministically() -> None:
    """Ordering must not depend on dictionary iteration — a ranking that
    reshuffles between identical runs is not a ranking."""
    entries = [_entry("zebra", 500.0), _entry("alpha", 500.0)]
    provenance = {"zebra": _prov(ConfidenceTier.C), "alpha": _prov(ConfidenceTier.C)}
    first = [g.parameter_path for g in _rank(entries, provenance).gaps]
    second = [g.parameter_path for g in _rank(list(reversed(entries)), provenance).gaps]
    assert first == second == ["alpha", "zebra"]
