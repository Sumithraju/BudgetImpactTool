"""Disease subgroups — M18 sections 5.1 to 5.4."""

from __future__ import annotations

import pytest

from biet_engine.constants import (
    SUBGROUP_PRIORITY,
    ConfidenceTier,
    FunnelStage,
    ResolutionLevel,
    Subgroup,
)
from biet_engine.exceptions import SubgroupAllocationError
from biet_engine.models import Provenance, SubgroupShare, Valued
from biet_engine.subgroups import allocate_shares, split_stage

PROVENANCE = Provenance(
    source="seeded co-prevalence",
    confidence_tier=ConfidenceTier.C,
    resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
)


def share(subgroup: Subgroup, value: float) -> SubgroupShare:
    return SubgroupShare(
        subgroup=subgroup, share=Valued(value=value, provenance=PROVENANCE)
    )


def four(cvd: float, t2d: float, htn: float, lipid: float) -> list[SubgroupShare]:
    return [
        share(Subgroup.OBESITY_ESTABLISHED_CVD, cvd),
        share(Subgroup.OBESITY_T2D, t2d),
        share(Subgroup.OBESITY_HYPERTENSION, htn),
        share(Subgroup.OBESITY_DYSLIPIDAEMIA, lipid),
    ]


# ------------------------------------------------------------- the residual


def test_obesity_alone_is_the_derived_residual() -> None:
    allocation, _ = allocate_shares(four(0.08, 0.19, 0.30, 0.05))
    assert allocation[Subgroup.OBESITY_ALONE] == pytest.approx(0.38)


def test_the_partition_always_sums_to_one() -> None:
    allocation, _ = allocate_shares(four(0.08, 0.19, 0.30, 0.13))
    assert sum(allocation.values()) == pytest.approx(1.0)


def test_supplying_obesity_alone_is_rejected() -> None:
    """The residual is arithmetic. Letting both be supplied invites a set that
    does not sum to one."""
    with pytest.raises(SubgroupAllocationError):
        allocate_shares([*four(0.08, 0.19, 0.30, 0.13), share(Subgroup.OBESITY_ALONE, 0.30)])


def test_paediatric_obesity_is_not_part_of_the_adult_partition() -> None:
    """It has its own denominator — the under-18 population — so it never
    enters the adult sum."""
    with pytest.raises(SubgroupAllocationError):
        allocate_shares([*four(0.08, 0.19, 0.30, 0.13), share(Subgroup.PAEDIATRIC_OBESITY, 0.05)])


def test_an_omitted_subgroup_is_a_zero_share_not_an_error() -> None:
    allocation, _ = allocate_shares(
        [share(Subgroup.OBESITY_T2D, 0.20), share(Subgroup.OBESITY_HYPERTENSION, 0.30)]
    )
    assert allocation[Subgroup.OBESITY_ESTABLISHED_CVD] == 0.0
    assert allocation[Subgroup.OBESITY_ALONE] == pytest.approx(0.50)


def test_every_subgroup_in_the_partition_is_present_in_the_result() -> None:
    allocation, _ = allocate_shares(four(0.08, 0.19, 0.30, 0.13))
    assert set(allocation) == set(SUBGROUP_PRIORITY)


# ----------------------------------------------------------------- bounds


def test_shares_reaching_one_leave_no_residual_and_raise() -> None:
    with pytest.raises(SubgroupAllocationError):
        allocate_shares(four(0.30, 0.30, 0.30, 0.10))


def test_shares_above_one_raise_under_strict() -> None:
    with pytest.raises(SubgroupAllocationError):
        allocate_shares(four(0.40, 0.40, 0.30, 0.10))


def test_shares_above_one_normalise_and_warn_when_not_strict() -> None:
    """M9's sweeps must not abort the analysis — M3's precedent."""
    allocation, warnings = allocate_shares(four(0.40, 0.40, 0.30, 0.10), strict=False)
    assert sum(allocation.values()) == pytest.approx(1.0)
    assert allocation[Subgroup.OBESITY_ALONE] == pytest.approx(0.0)
    assert [w.code for w in warnings] == ["SUBGROUP_SHARES_NORMALISED"]


def test_a_negative_share_is_rejected() -> None:
    with pytest.raises(SubgroupAllocationError):
        allocate_shares(four(-0.01, 0.19, 0.30, 0.13))


def test_a_share_above_one_on_its_own_is_rejected() -> None:
    with pytest.raises(SubgroupAllocationError):
        allocate_shares([share(Subgroup.OBESITY_T2D, 1.4)])


# ------------------------------------------------------------ splitting


def test_segment_patients_sum_back_to_the_stage_total() -> None:
    """A breakdown that does not reconcile to the figure it breaks down is
    worse than no breakdown."""
    allocation = split_stage(FunnelStage.DISEASED, 14_132_208, four(0.08, 0.19, 0.30, 0.13))
    assert sum(s.patients for s in allocation.segments) == pytest.approx(14_132_208)


def test_segments_come_back_in_priority_order() -> None:
    allocation = split_stage(FunnelStage.DISEASED, 1_000.0, four(0.08, 0.19, 0.30, 0.13))
    assert [s.subgroup for s in allocation.segments] == list(SUBGROUP_PRIORITY)


def test_the_residual_segment_is_flagged_as_derived() -> None:
    allocation = split_stage(FunnelStage.DISEASED, 1_000.0, four(0.08, 0.19, 0.30, 0.13))
    residual = next(s for s in allocation.segments if s.is_residual)
    assert residual.subgroup is Subgroup.OBESITY_ALONE
    assert [s.is_residual for s in allocation.segments].count(True) == 1


def test_a_supplied_segment_keeps_its_own_provenance() -> None:
    """Provenance never drops — non-negotiable 8."""
    allocation = split_stage(FunnelStage.DISEASED, 1_000.0, four(0.08, 0.19, 0.30, 0.13))
    t2d = next(s for s in allocation.segments if s.subgroup is Subgroup.OBESITY_T2D)
    assert t2d.provenance.source == "seeded co-prevalence"


def test_the_residual_carries_synthetic_provenance_not_a_borrowed_one() -> None:
    allocation = split_stage(FunnelStage.DISEASED, 1_000.0, four(0.08, 0.19, 0.30, 0.13))
    residual = next(s for s in allocation.segments if s.is_residual)
    assert "derived residual" in residual.provenance.source
    assert residual.provenance.confidence_tier is ConfidenceTier.C


def test_a_zero_stage_total_splits_into_zero_segments_without_dividing() -> None:
    allocation = split_stage(FunnelStage.DISEASED, 0.0, four(0.08, 0.19, 0.30, 0.13))
    assert all(s.patients == 0.0 for s in allocation.segments)
    assert sum(s.share for s in allocation.segments) == pytest.approx(1.0)


def test_moving_share_between_subgroups_moves_patients_the_same_way() -> None:
    base = split_stage(FunnelStage.DISEASED, 1_000_000.0, four(0.08, 0.19, 0.30, 0.13))
    sicker = split_stage(FunnelStage.DISEASED, 1_000_000.0, four(0.13, 0.19, 0.30, 0.13))

    def patients(allocation, subgroup: Subgroup) -> float:
        return next(s.patients for s in allocation.segments if s.subgroup is subgroup)

    assert patients(sicker, Subgroup.OBESITY_ESTABLISHED_CVD) > patients(
        base, Subgroup.OBESITY_ESTABLISHED_CVD
    )
    # It comes out of the residual, not out of thin air.
    assert patients(sicker, Subgroup.OBESITY_ALONE) < patients(base, Subgroup.OBESITY_ALONE)
    assert sum(s.patients for s in sicker.segments) == pytest.approx(
        sum(s.patients for s in base.segments)
    )
