"""Evidence-Gap Priority — ARCHITECTURE.md section 5.12, module M15.

Sensitivity says which assumptions move the answer. Confidence tiers say which
assumptions are weakly founded. Neither alone answers the question an analyst
actually has after reading a tornado diagram, which is not "what is uncertain"
but "what should I go and find out". Their product does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .constants import (
    EVIDENCE_PRIORITY_THRESHOLDS,
    TIER_WEAKNESS,
    ConfidenceTier,
    EvidencePriority,
)
from .models import EvidenceGap, EvidenceGapReport, Money, OwsaEntry, Provenance


def _band(score: float) -> EvidencePriority:
    for priority, threshold in EVIDENCE_PRIORITY_THRESHOLDS.items():
        if score >= threshold:
            return priority
    return EvidencePriority.SUFFICIENT


def rank_evidence_gaps(
    entries: Sequence[OwsaEntry],
    provenance: Mapping[str, Provenance],
    *,
    currency: str,
) -> EvidenceGapReport:
    """Rank parameters by how much they move the answer times how weak they are.

        influence = swing / max(swing)
        priority  = influence x weakness(tier)

    Normalising by the maximum swing rather than by total budget impact makes
    the ranking scale-free and comparable across scenarios and markets, at the
    cost of the top parameter's influence always being exactly 1.0. That is
    acceptable because the output is an ordering, not a magnitude.

    A parameter with zero swing scores zero however weak its source. This is
    the point of the module and not a limitation of it: time spent pinning
    down a value that cannot move the result is time not spent on the one that
    can.

    A parameter with no provenance is treated as tier D and flagged. An
    unattributed value is a placeholder by definition — whatever number is in
    it — and the ranking should say so rather than quietly assume the best.

    Args:
        entries: M9's one-way sensitivity result.
        provenance: `parameter_path -> provenance`, for the tier and source.
        currency: reporting currency, for the returned swings.

    Returns:
        Gaps ranked highest priority first, ties broken deterministically.
    """
    if not entries:
        return EvidenceGapReport(gaps=(), max_swing=Money(amount=0.0, currency=currency))

    max_swing = max(e.swing for e in entries)

    gaps: list[EvidenceGap] = []
    for entry in entries:
        origin = provenance.get(entry.parameter_path)
        tier = origin.confidence_tier if origin else ConfidenceTier.D
        weakness = TIER_WEAKNESS[tier]

        # Every swing being zero is a real state — a scenario where nothing
        # moves the answer — and must not divide by zero on the way to
        # saying so.
        influence = entry.swing / max_swing if max_swing > 0 else 0.0
        score = influence * weakness

        gaps.append(EvidenceGap(
            parameter_path=entry.parameter_path,
            label=entry.label,
            swing=Money(amount=entry.swing, currency=currency),
            influence=influence,
            confidence_tier=tier,
            weakness=weakness,
            priority_score=score,
            priority=_band(score),
            source=origin.source if origin else "no stated source",
            has_provenance=origin is not None,
        ))

    # Ties break by descending swing then by path, so the ordering is stable
    # across runs rather than dependent on dictionary iteration.
    gaps.sort(key=lambda g: (-g.priority_score, -g.swing.amount, g.parameter_path))
    return EvidenceGapReport(
        gaps=tuple(gaps), max_swing=Money(amount=max_swing, currency=currency),
    )
