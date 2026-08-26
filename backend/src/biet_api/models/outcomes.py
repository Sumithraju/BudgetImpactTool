"""Clinical outcomes and disease subgroups — M16 and M18, ARCHITECTURE.md §4B.

Four catalogues, and the design point that connects them: **a baseline event
rate belongs to the subgroup, never to the therapy**. Obesity with established
cardiovascular disease carries a materially higher annual MACE rate than
obesity alone, and one averaged rate describes neither population. The therapy
supplies only the *relative* reduction it was observed to produce; the
population supplies the rate that reduction applies to.

That split is what lets `treatment_effects` stay small and honest — one row per
therapy per event class, each naming its trial — while the same trial-observed
reduction produces different avoided-event counts in different subgroups.

`confidence_tier` carries no default anywhere in this module. An effect size is
the value in this system most likely to be repeated as fact in a slide, so it
cannot be written without one.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ConfidenceTierCol, CountryCode, CurrencyCode, Quantity, Rate


class DiseaseSubgroup(Base):
    """One clinically distinct population inside a disease — M18.

    A subgroup is a *scenario dimension*, not an engine contract: the engine
    runs unchanged once per segment and the results aggregate. That is what
    keeps `biet_engine` pure and lets each segment carry its own comparator
    mix and its own outcome profile.

    `share_of_diagnosed` is the subgroup's share of the prevalent diseased
    population. Whether those shares may be **added** is the single most
    important thing this table records, and it is what `is_overlapping` says.

    The WHO-derived obesity subgroups overlap: a patient with both type 2
    diabetes and hypertension appears in the diabesity subgroup and in the
    hypertension/sleep-apnoea subgroup, and across the ten source countries the
    four shares sum to roughly 1.5x the obese population. Overlapping subgroups
    are therefore **alternative eligibility definitions to be compared, never
    components of a total to be added** — and a model that summed them would
    overstate the treated population by half without anything erroring.
    """

    __tablename__ = "disease_subgroups"

    subgroup_id: Mapped[int] = mapped_column(primary_key=True)
    indication_id: Mapped[int] = mapped_column(
        ForeignKey("indications.indication_id", ondelete="CASCADE")
    )
    subgroup_code: Mapped[str] = mapped_column(Text)
    subgroup_label: Mapped[str] = mapped_column(Text)
    #: What the segment is, in one sentence, for the interface's hover text.
    description: Mapped[str | None] = mapped_column(Text)

    share_of_diagnosed: Mapped[Rate] = mapped_column(Numeric(6, 5))
    #: An additional eligibility multiplier applied on top of the indication's
    #: shared criterion stack. 1.0 means the segment is no more or less
    #: label-eligible than the disease population as a whole.
    eligible_factor: Mapped[Rate] = mapped_column(Numeric(6, 4), default=1)
    #: Relative uptake against the scenario's curve. A segment with a stronger
    #: clinical rationale is adopted faster; this is where that is said.
    uptake_multiplier: Mapped[Quantity] = mapped_column(Numeric(6, 4), default=1)

    #: True for the row standing for the whole diseased population — the
    #: denominator every other subgroup's share is a share of, and the
    #: population a run models when no subgroup is chosen. Excluded from the
    #: selectable list, because "all of them" is not a restriction.
    is_default_population: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(),
    )
    #: True when this subgroup shares patients with its siblings. Selecting more
    #: than one overlapping subgroup is refused rather than summed; see the
    #: class docstring.
    is_overlapping: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(),
    )

    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    #: No default. See the module docstring.
    confidence_tier: Mapped[ConfidenceTierCol]

    event_rates: Mapped[list[SubgroupEventRate]] = relationship(
        back_populates="subgroup", cascade="all, delete-orphan"
    )
    country_rates: Mapped[list[SubgroupCountryRate]] = relationship(
        back_populates="subgroup", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "indication_id", "subgroup_code", name="uq_disease_subgroups_natural"
        ),
        CheckConstraint(
            "share_of_diagnosed > 0 AND share_of_diagnosed <= 1",
            name="ck_disease_subgroups_share",
        ),
        CheckConstraint(
            "eligible_factor > 0 AND eligible_factor <= 1",
            name="ck_disease_subgroups_eligible",
        ),
        CheckConstraint("uptake_multiplier > 0", name="ck_disease_subgroups_uptake"),
    )


class SubgroupCountryRate(Base):
    """One subgroup's share and eligibility in one market — M18.

    The share is a property of the market, not of the disease. WHO's own
    indicators make that concrete: the hypertension/sleep-apnoea subgroup is
    56% of obese adults in Brazil and 43% in France, because their published
    hypertension prevalences differ by a third. Carrying one global figure
    would apply Brazil's comorbidity burden to France.

    A market with no row here falls back to `DiseaseSubgroup.share_of_diagnosed`,
    which is the mean across the markets that do have one — a stated
    approximation, and labelled as one.
    """

    __tablename__ = "subgroup_country_rates"

    rate_id: Mapped[int] = mapped_column(primary_key=True)
    subgroup_id: Mapped[int] = mapped_column(
        ForeignKey("disease_subgroups.subgroup_id", ondelete="CASCADE")
    )
    country_code: Mapped[CountryCode] = mapped_column(
        ForeignKey("countries.country_code")
    )
    share_of_diagnosed: Mapped[Rate] = mapped_column(Numeric(6, 5))
    eligible_factor: Mapped[Rate] = mapped_column(Numeric(6, 4))
    source: Mapped[str] = mapped_column(Text)
    confidence_tier: Mapped[ConfidenceTierCol]

    subgroup: Mapped[DiseaseSubgroup] = relationship(back_populates="country_rates")

    __table_args__ = (
        UniqueConstraint(
            "subgroup_id", "country_code", name="uq_subgroup_country_rates_natural"
        ),
        CheckConstraint(
            "share_of_diagnosed > 0 AND share_of_diagnosed <= 1",
            name="ck_subgroup_country_rates_share",
        ),
        CheckConstraint(
            "eligible_factor > 0 AND eligible_factor <= 1",
            name="ck_subgroup_country_rates_eligible",
        ),
    )


class CountryHealthIndicator(Base):
    """One published health indicator for one market — WHO GHO.

    Distinct from `country_economics`, which holds World Bank macroeconomics.
    These are the disease-burden figures a market-access reader recognises:
    obesity prevalence by sex, diabetes prevalence and treatment coverage,
    hypertension prevalence.

    `indicator_kind` separates **prevalence** (the share of a population that
    has a condition at a point in time) from **coverage** (the share of those
    receiving treatment) from **policy** (a categorical status with no numeric
    value). Keeping the kind on the row is what stops a prevalence being read
    as an incidence downstream — they are different quantities with different
    units, and the whole outcomes layer depends on not confusing them.
    """

    __tablename__ = "country_health_indicators"

    indicator_id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[CountryCode] = mapped_column(
        ForeignKey("countries.country_code")
    )
    indicator: Mapped[str] = mapped_column(Text)
    indicator_kind: Mapped[str] = mapped_column(Text)
    #: NULL for a categorical indicator, which carries its value in `label`.
    value: Mapped[Rate | None] = mapped_column(Numeric(8, 6))
    label: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    vintage_year: Mapped[int | None] = mapped_column(SmallInteger)
    confidence_tier: Mapped[ConfidenceTierCol]

    __table_args__ = (
        UniqueConstraint(
            "country_code", "indicator", name="uq_country_health_indicators_natural"
        ),
        CheckConstraint(
            "value IS NULL OR (value >= 0 AND value <= 1)",
            name="ck_country_health_indicators_fraction",
        ),
    )


class SubgroupEventRate(Base):
    """The annual INCIDENCE of one clinical event in one subgroup, on current care.

    **Incidence, not prevalence.** This is the number of *new* events per year
    in a population that has not yet had them — not the share of the population
    already affected. The distinction is load-bearing: multiplying a prevalence
    by a relative risk reduction and calling the product "events avoided" would
    credit the therapy with preventing conditions the patients already have.

    This is the denominator every avoided-event count is built on, and it is
    the reason subgroups exist as a first-class concept rather than as a label
    on a scenario. A 2.4% annual MACE incidence in secondary prevention against
    0.8% across obesity as a whole is a factor of three, and it flows straight
    through to what the payer is told the spend buys.
    """

    __tablename__ = "subgroup_event_rates"

    rate_id: Mapped[int] = mapped_column(primary_key=True)
    subgroup_id: Mapped[int] = mapped_column(
        ForeignKey("disease_subgroups.subgroup_id", ondelete="CASCADE")
    )
    event_class: Mapped[str] = mapped_column(Text)
    baseline_annual_rate: Mapped[Rate] = mapped_column(Numeric(7, 6))
    rate_low: Mapped[Rate | None] = mapped_column(Numeric(7, 6))
    rate_high: Mapped[Rate | None] = mapped_column(Numeric(7, 6))
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    vintage_year: Mapped[int | None] = mapped_column(SmallInteger)
    confidence_tier: Mapped[ConfidenceTierCol]

    subgroup: Mapped[DiseaseSubgroup] = relationship(back_populates="event_rates")

    __table_args__ = (
        UniqueConstraint(
            "subgroup_id", "event_class", name="uq_subgroup_event_rates_natural"
        ),
        CheckConstraint(
            "baseline_annual_rate >= 0 AND baseline_annual_rate <= 1",
            name="ck_subgroup_event_rates_range",
        ),
    )


class TreatmentEffect(Base):
    """One therapy's observed relative risk reduction on one event class — M16.

    Relative, never absolute: an absolute reduction observed in a trial
    population cannot be transported to a population with a different baseline
    rate, and transporting it anyway is the single most common way a budget
    impact model overstates what a therapy buys.

    `trial` is mandatory and is not a formality. M16's rule is that nothing is
    inferred: no effect is derived from a drug class, from a mechanism, or from
    another therapy's result. A row without a trial has nothing behind it.
    """

    __tablename__ = "treatment_effects"

    effect_id: Mapped[int] = mapped_column(primary_key=True)
    drug_id: Mapped[int] = mapped_column(
        ForeignKey("drugs.drug_id", ondelete="CASCADE")
    )
    event_class: Mapped[str] = mapped_column(Text)
    relative_reduction: Mapped[Rate] = mapped_column(Numeric(6, 5))
    reduction_low: Mapped[Rate | None] = mapped_column(Numeric(6, 5))
    reduction_high: Mapped[Rate | None] = mapped_column(Numeric(6, 5))
    #: Which segment the effect was observed in, where the trial enrolled one.
    #: Null means it is applied across every segment, which is an assumption
    #: and is stated as one in the assumption register.
    observed_in_subgroup: Mapped[str | None] = mapped_column(Text)
    trial: Mapped[str] = mapped_column(Text)
    nct_id: Mapped[str | None] = mapped_column(Text)
    #: The trial's follow-up. A horizon longer than this is an extrapolation,
    #: and the engine says so (`EFFECT_BEYOND_FOLLOW_UP`) rather than quietly
    #: projecting past what was observed.
    follow_up_weeks: Mapped[int | None] = mapped_column(SmallInteger)
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    vintage_year: Mapped[int | None] = mapped_column(SmallInteger)
    confidence_tier: Mapped[ConfidenceTierCol]

    __table_args__ = (
        UniqueConstraint(
            "drug_id", "event_class", name="uq_treatment_effects_natural"
        ),
        CheckConstraint(
            "relative_reduction >= 0 AND relative_reduction < 1",
            name="ck_treatment_effects_range",
        ),
    )


class EventCost(Base):
    """What one occurrence of a clinical event costs a payer, per market.

    Distinct from `adverse_event_costs`: that catalogue prices the side effects
    a therapy *causes*, this one prices the events it *avoids*. They sit on
    opposite sides of the ledger and conflating them would net two unrelated
    quantities against each other.
    """

    __tablename__ = "event_costs"

    event_cost_id: Mapped[int] = mapped_column(primary_key=True)
    event_class: Mapped[str] = mapped_column(Text)
    country_code: Mapped[CountryCode] = mapped_column(
        ForeignKey("countries.country_code")
    )
    unit_cost_local: Mapped[Quantity]
    currency_code: Mapped[CurrencyCode]
    cost_year: Mapped[int | None] = mapped_column(SmallInteger)
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    confidence_tier: Mapped[ConfidenceTierCol]

    __table_args__ = (
        UniqueConstraint(
            "event_class", "country_code", name="uq_event_costs_natural"
        ),
        CheckConstraint("unit_cost_local >= 0", name="ck_event_costs_non_negative"),
    )


class ResponseProfile(Base):
    """The proportion of patients reaching a weight-loss threshold, and regain.

    Separate from `treatment_effects` because a responder share is not an event
    avoided — it is the clinical result the payer was promised, reported in the
    units the trial reported it in. `regain_per_year` is what decays it: a
    trial's reported effect *is* the year-one effect, so it is applied in full
    in year 1 and decays only from year 2.
    """

    __tablename__ = "response_profiles"

    profile_id: Mapped[int] = mapped_column(primary_key=True)
    drug_id: Mapped[int] = mapped_column(
        ForeignKey("drugs.drug_id", ondelete="CASCADE")
    )
    threshold: Mapped[str] = mapped_column(Text)
    responder_share: Mapped[Rate] = mapped_column(Numeric(6, 5))
    responder_low: Mapped[Rate | None] = mapped_column(Numeric(6, 5))
    responder_high: Mapped[Rate | None] = mapped_column(Numeric(6, 5))
    mean_weight_loss_pct: Mapped[Quantity] = mapped_column(Numeric(6, 3))
    regain_per_year: Mapped[Rate] = mapped_column(Numeric(6, 5), default=0)
    trial: Mapped[str] = mapped_column(Text)
    nct_id: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    vintage_year: Mapped[int | None] = mapped_column(SmallInteger)
    confidence_tier: Mapped[ConfidenceTierCol]

    __table_args__ = (
        UniqueConstraint("drug_id", "threshold", name="uq_response_profiles_natural"),
        CheckConstraint(
            "responder_share >= 0 AND responder_share <= 1",
            name="ck_response_profiles_share",
        ),
        CheckConstraint(
            "regain_per_year >= 0 AND regain_per_year <= 1",
            name="ck_response_profiles_regain",
        ),
    )


__all__ = [
    "CountryHealthIndicator",
    "DiseaseSubgroup",
    "EventCost",
    "ResponseProfile",
    "SubgroupCountryRate",
    "SubgroupEventRate",
    "TreatmentEffect",
]
