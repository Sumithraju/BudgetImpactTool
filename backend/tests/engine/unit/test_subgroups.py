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


# ------------------------------------------------------------ aggregation

from biet_engine.impact import compute_budget_impact
from biet_engine.subgroups import aggregate_segments

from ..conftest import (
    make_country_input,
    make_criterion,
    make_engine_input,
    make_therapy_input,
    make_uptake_input,
    make_valued,
)

#: The canonical Germany case, at whatever share of the diseased population is
#: asked for. Scaling prevalence scales the `diseased` stage and nothing else,
#: which is exactly what a subgroup is: a slice of the people who have the
#: disease, running through the same funnel beneath it.
GOLDEN_PREVALENCE = 0.2064


def golden_engine_input(share: float = 1.0, *, price: float = 4800.0):
    new_therapy = make_therapy_input(
        drug_id=2, is_new=True, unit_price=price, currency="EUR", admins_per_year=1.0
    ).model_copy(update={"persistence_12m": make_valued(0.50)})
    comparator = make_therapy_input(
        drug_id=1, is_new=False, unit_price=1200.0, currency="EUR", admins_per_year=1.0
    ).model_copy(update={"persistence_12m": make_valued(0.70)})

    from biet_engine.models import Substitution

    country = make_country_input(
        country_code="DEU", currency="EUR",
        population_total=83_500_000, adult_share=0.820,
        prevalence=GOLDEN_PREVALENCE * share,
        diagnosis_rate=0.600, treatment_rate=0.150, access_rate=0.700,
        criteria=(make_criterion("synthetic_stack", 0.350),),
        horizon=3, therapies=(comparator,), new_therapy=new_therapy,
        baseline_shares={1: (1.0, 1.0, 1.0)},
        substitution=Substitution(shares={1: make_valued(1.0)}),
    )
    return make_engine_input(
        countries=(country,), horizon_years=3, reporting_currency="EUR",
        fx_rates={"EUR": 1.0, "USD": 0.86386},
        uptake=make_uptake_input(vector=(0.05, 0.12, 0.20)),
    )


SPLIT = {
    Subgroup.OBESITY_ESTABLISHED_CVD: 0.08,
    Subgroup.OBESITY_T2D: 0.19,
    Subgroup.OBESITY_HYPERTENSION: 0.30,
    Subgroup.OBESITY_DYSLIPIDAEMIA: 0.13,
    Subgroup.OBESITY_ALONE: 0.30,
}


def run_split(shares: dict[Subgroup, float]):
    return aggregate_segments([
        (subgroup, s, compute_budget_impact(golden_engine_input(s)))
        for subgroup, s in shares.items()
    ])


def test_a_uniform_split_reproduces_the_undifferentiated_total_exactly() -> None:
    """The test this whole design is exposed to.

    If splitting a population into segments that all carry identical inputs
    changes the total, the aggregation is wrong.
    """
    whole = compute_budget_impact(golden_engine_input(1.0)).totals
    split = run_split(SPLIT).totals

    assert split.cumulative.amount == pytest.approx(whole.cumulative.amount, rel=1e-9)
    for year, (a, b) in enumerate(zip(split.by_year, whole.by_year, strict=True), 1):
        assert a.amount == pytest.approx(b.amount, rel=1e-9), f"year {year}"


def test_both_worlds_survive_aggregation_across_segments() -> None:
    whole = compute_budget_impact(golden_engine_input(1.0)).totals
    split = run_split(SPLIT).totals

    assert split.without_by_year[0].amount == pytest.approx(
        whole.without_by_year[0].amount, rel=1e-9
    )
    assert split.with_by_year[0].amount - split.without_by_year[0].amount == pytest.approx(
        split.by_year[0].amount, rel=1e-9
    )


def test_contributions_sum_to_one_when_every_segment_adds_cost() -> None:
    aggregate = run_split(SPLIT)
    assert sum(c.share_of_total_impact for c in aggregate.contributions) == pytest.approx(1.0)


def test_a_larger_segment_contributes_more_than_a_smaller_one() -> None:
    aggregate = run_split(SPLIT)
    by_subgroup = {c.subgroup: c for c in aggregate.contributions}
    assert (
        by_subgroup[Subgroup.OBESITY_HYPERTENSION].share_of_total_impact
        > by_subgroup[Subgroup.OBESITY_ESTABLISHED_CVD].share_of_total_impact
    )


def test_patients_sum_across_segments_to_the_undifferentiated_count() -> None:
    whole = compute_budget_impact(golden_engine_input(1.0))
    aggregate = run_split(SPLIT)

    assert sum(c.patients_on_new_final_year for c in aggregate.contributions) == pytest.approx(
        whole.countries[0].years[-1].patients_on_new, rel=1e-9
    )


def test_peak_year_is_recomputed_from_the_aggregate() -> None:
    """Not inherited from any one segment."""
    aggregate = run_split(SPLIT)
    peak = max(range(1, 4), key=lambda y: aggregate.totals.by_year[y - 1].amount)
    assert aggregate.totals.peak_year == peak


def test_mixed_sign_segments_warn_that_shares_are_not_proportions() -> None:
    """A cost-saving segment beside a cost-adding one makes 'share of total'
    read as a proportion when it is not one."""
    aggregate = aggregate_segments([
        # Priced above the comparator: adds cost.
        (Subgroup.OBESITY_T2D, 0.5, compute_budget_impact(golden_engine_input(0.5))),
        # Priced below it: saves cost.
        (Subgroup.OBESITY_ALONE, 0.5,
         compute_budget_impact(golden_engine_input(0.5, price=100.0))),
    ])
    assert "MIXED_SIGN_SEGMENTS" in {w.code for w in aggregate.warnings}


def test_segments_spanning_different_horizons_are_rejected() -> None:
    from biet_engine.models import Substitution

    short = make_engine_input(
        countries=(make_country_input(
            country_code="DEU", currency="EUR",
            population_total=83_500_000, adult_share=0.820, prevalence=0.1,
            diagnosis_rate=0.6, treatment_rate=0.15, access_rate=0.7,
            criteria=(make_criterion("s", 0.35),),
            horizon=1,
            therapies=(make_therapy_input(drug_id=1, is_new=False, unit_price=1200.0,
                                          currency="EUR", admins_per_year=1.0),),
            new_therapy=make_therapy_input(drug_id=2, is_new=True, unit_price=4800.0,
                                           currency="EUR", admins_per_year=1.0),
            baseline_shares={1: (1.0,)},
            substitution=Substitution(shares={1: make_valued(1.0)}),
        ),),
        horizon_years=1, reporting_currency="EUR",
        fx_rates={"EUR": 1.0, "USD": 0.86386},
        uptake=make_uptake_input(vector=(0.05,)),
    )
    with pytest.raises(SubgroupAllocationError):
        aggregate_segments([
            (Subgroup.OBESITY_T2D, 0.5, compute_budget_impact(short)),
            (Subgroup.OBESITY_ALONE, 0.5, compute_budget_impact(golden_engine_input(0.5))),
        ])


def test_aggregating_nothing_is_rejected() -> None:
    with pytest.raises(SubgroupAllocationError):
        aggregate_segments([])
