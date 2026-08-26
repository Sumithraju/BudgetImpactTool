"""Disease Subgroups — ARCHITECTURE.md module M18.

One disease, and the clinically distinct populations inside it. Obesity with
established cardiovascular disease is not obesity with type 2 diabetes, and
neither is obesity alone: they differ in how many people are in them, in what
fraction is eligible, in what they are currently treated with, and — most
consequentially — in the events a therapy avoids. An averaged population
produces a number that describes nobody.

**The engine is not changed by this module.** `compute_funnel` and every other
signature stays as it is; a subgroup is a *scenario dimension*, so the service
layer loops and this module allocates and aggregates. That is what keeps
`biet_engine` pure and lets each segment carry its own comparator mix.
"""

from __future__ import annotations

from collections.abc import Sequence

from .constants import (
    RATE_MAX,
    RATE_MIN,
    SUBGROUP_PRIORITY,
    SUPPLIED_SUBGROUPS,
    ConfidenceTier,
    FunnelStage,
    ResolutionLevel,
    Subgroup,
)
from .exceptions import SubgroupAllocationError
from .models import (
    Provenance,
    SubgroupAllocation,
    SubgroupSegment,
    SubgroupShare,
    Warning_,
)

#: Provenance for the derived residual. Synthetic — it is arithmetic, not a
#: resolved value — and tier C rather than claiming a stronger basis than the
#: shares it is computed from.
_RESIDUAL_PROVENANCE = Provenance(
    source="derived residual — 1 minus the supplied comorbidity shares",
    confidence_tier=ConfidenceTier.C,
    resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
    note="M18 section 5.2",
)


def allocate_shares(
    shares: Sequence[SubgroupShare], *, strict: bool = True
) -> tuple[dict[Subgroup, float], tuple[Warning_, ...]]:
    """Turn supplied comorbidity shares into an exclusive, exhaustive partition.

        share(OBESITY_ALONE) = 1 - sum of the four supplied shares

    A patient with obesity, type 2 diabetes and hypertension appears in every
    prevalence statistic for all three. Allocating each patient to the first
    subgroup in `SUBGROUP_PRIORITY` whose definition they meet is what stops
    them being counted three times, and it is why the supplied shares must sum
    to strictly less than one.

    `OBESITY_ALONE` is derived and may not be supplied: the residual is
    arithmetic, and permitting both invites a set that does not sum to one.
    `PAEDIATRIC_OBESITY` is disjoint from this partition — it has its own
    denominator — and is rejected here rather than silently folded in.

    Args:
        shares: supplied shares for the four comorbidity subgroups. A subgroup
            omitted entirely is treated as a zero share, which is the correct
            reading of "this market has no such segment modelled".
        strict: when True (the default, for API calls), a supplied total at or
            above 1.0 raises. When False — M9's sensitivity sweeps, matching
            M3's precedent, where raising would abort the analysis — the shares
            are normalised to leave a zero residual and a warning is returned.

    Returns:
        Every subgroup in `SUBGROUP_PRIORITY` mapped to its share, and any
        warnings raised along the way.

    Raises:
        SubgroupAllocationError: a share outside [0, 1]; `OBESITY_ALONE` or
            `PAEDIATRIC_OBESITY` supplied; or, under `strict`, a supplied
            total at or above 1.0.
    """
    supplied: dict[Subgroup, float] = {}
    warnings: list[Warning_] = []

    for entry in shares:
        if entry.subgroup not in SUPPLIED_SUBGROUPS:
            raise SubgroupAllocationError(
                f"{entry.subgroup.value} cannot be supplied: "
                f"{Subgroup.OBESITY_ALONE.value} is the derived residual and "
                f"{Subgroup.PAEDIATRIC_OBESITY.value} has its own denominator",
                subgroup=entry.subgroup.value,
            )
        if not (RATE_MIN <= entry.share.value <= RATE_MAX):
            raise SubgroupAllocationError(
                f"{entry.subgroup.value} share {entry.share.value} is outside [0, 1]",
                subgroup=entry.subgroup.value,
            )
        supplied[entry.subgroup] = entry.share.value

    total = sum(supplied.values())

    if total >= RATE_MAX:
        if strict:
            raise SubgroupAllocationError(
                f"comorbidity shares total {total:.4f}, leaving no residual for "
                f"{Subgroup.OBESITY_ALONE.value}; they must sum to less than 1",
                total=total,
            )
        # A sweep that pushes one share high must not abort the analysis.
        supplied = {k: v / total for k, v in supplied.items()}
        total = RATE_MAX
        warnings.append(
            Warning_(
                code="SUBGROUP_SHARES_NORMALISED",
                message=(
                    f"Comorbidity shares totalled {total:.1%} or more and were "
                    f"normalised; obesity alone is left at zero."
                ),
            )
        )

    allocation = {subgroup: supplied.get(subgroup, 0.0) for subgroup in SUPPLIED_SUBGROUPS}
    allocation[Subgroup.OBESITY_ALONE] = RATE_MAX - total
    return allocation, tuple(warnings)


def split_stage(
    stage: FunnelStage,
    total: float,
    shares: Sequence[SubgroupShare],
    *,
    strict: bool = True,
) -> SubgroupAllocation:
    """Divide one funnel stage across the subgroup partition.

    Patient counts are the stage total times each share, so they sum back to
    the stage total exactly — a breakdown that does not reconcile to the figure
    it breaks down is worse than no breakdown.

    Args:
        stage: which funnel stage is being split. Splitting `DISEASED` is the
            usual case: the partition is of the adult population *with the
            disease*, so applying it further up would divide people who do not
            have obesity across obesity subgroups.
        total: the stage's patient count.
        shares: as `allocate_shares`.
        strict: as `allocate_shares`.
    """
    allocation, warnings = allocate_shares(shares, strict=strict)
    supplied_provenance = {entry.subgroup: entry.share.provenance for entry in shares}

    segments = tuple(
        SubgroupSegment(
            subgroup=subgroup,
            share=share,
            patients=total * share,
            is_residual=subgroup is Subgroup.OBESITY_ALONE,
            provenance=supplied_provenance.get(subgroup, _RESIDUAL_PROVENANCE),
        )
        for subgroup, share in ((s, allocation[s]) for s in SUBGROUP_PRIORITY)
    )

    return SubgroupAllocation(
        stage=stage, total=total, segments=segments, warnings=warnings
    )
