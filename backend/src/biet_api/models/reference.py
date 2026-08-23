"""Reference data — ARCHITECTURE.md section 8.1.

Populated by the M0 ingestion pipeline. Read by every downstream module through
repositories; never queried directly from a service.

Every published row carries `source` and `confidence_tier`. That is not a
convention, it is the mechanism by which provenance reaches the interface
(non-negotiable 8). A column pair without them is a defect.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..constants.domain import ConfidenceTier
from .base import (
    Base,
    ConfidenceTierCol,
    CountryCode,
    CurrencyCode,
    Percent,
    Quantity,
    Rate,
)

# Ranges asserted in the database, not merely in Python, so a bad row cannot be
# written by any path — including a migration backfill or a manual fix.
_ADULT_SHARE_MIN = 0.50
_ADULT_SHARE_MAX = 0.95


class Country(Base):
    __tablename__ = "countries"

    country_code: Mapped[CountryCode] = mapped_column(primary_key=True)
    country_name: Mapped[str] = mapped_column(Text)
    currency_code: Mapped[CurrencyCode]
    region: Mapped[str | None] = mapped_column(Text)
    health_system_type: Mapped[str | None] = mapped_column(Text)

    # 18+ share of total population. Derived from the World Bank 0-14 band with
    # the 15-17 cohort removed, because WHO prevalence is 18+ (M0 section 5.2).
    adult_share: Mapped[Rate] = mapped_column(Numeric(5, 4))
    adult_share_source: Mapped[str] = mapped_column(Text)
    adult_share_confidence_tier: Mapped[ConfidenceTierCol] = mapped_column(
        default=ConfidenceTier.B.value
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint(
            f"adult_share > {_ADULT_SHARE_MIN} AND adult_share < {_ADULT_SHARE_MAX}",
            name="ck_countries_adult_share_range",
        ),
    )


class CountryEconomics(Base):
    """One row per country per indicator, each at its own resolved vintage year.

    The vintage differs per indicator: population reaches 2025 while health
    expenditure lags to 2023/2024. Joining on a fixed year silently discards
    health expenditure for every market (ARCHITECTURE.md section 7.2).
    """

    __tablename__ = "country_economics"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[CountryCode] = mapped_column(
        ForeignKey("countries.country_code")
    )
    indicator: Mapped[str] = mapped_column(Text)
    year: Mapped[int] = mapped_column(SmallInteger)
    value: Mapped[Quantity]
    source: Mapped[str] = mapped_column(Text)
    confidence_tier: Mapped[ConfidenceTierCol] = mapped_column(
        default=ConfidenceTier.A.value
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "country_code", "indicator", "year", name="uq_country_economics_natural"
        ),
    )


class Indication(Base):
    __tablename__ = "indications"

    indication_id: Mapped[int] = mapped_column(primary_key=True)
    indication_name: Mapped[str] = mapped_column(Text, unique=True)
    therapy_area: Mapped[str] = mapped_column(Text)
    icd10: Mapped[str | None] = mapped_column(Text)
    who_indicator_code: Mapped[str | None] = mapped_column(Text)
    default_horizon: Mapped[int] = mapped_column(SmallInteger, default=3)


class Epidemiology(Base):
    """Prevalence with the source's own confidence interval.

    `prevalence_low` / `prevalence_high` are WHO's published bounds and are what
    M9 uses to parameterise the PSA. Discarding them is a defect.
    """

    __tablename__ = "epidemiology"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[CountryCode] = mapped_column(
        ForeignKey("countries.country_code")
    )
    indication_id: Mapped[int] = mapped_column(
        ForeignKey("indications.indication_id")
    )
    year: Mapped[int] = mapped_column(SmallInteger)
    prevalence_pct: Mapped[Percent]
    prevalence_low: Mapped[Percent | None]
    prevalence_high: Mapped[Percent | None]
    age_group: Mapped[str] = mapped_column(Text, default="AGEGROUP_YEARS18-PLUS")
    sex: Mapped[str] = mapped_column(Text, default="SEX_BTSX")
    source: Mapped[str] = mapped_column(Text)
    confidence_tier: Mapped[ConfidenceTierCol]

    # True for a row extrapolated forward from a stale observation. Any run
    # consuming one emits a STALE_VINTAGE warning (M0 section 5.3).
    is_projected: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint(
            "country_code",
            "indication_id",
            "year",
            "age_group",
            "sex",
            name="uq_epidemiology_natural",
        ),
        CheckConstraint(
            "prevalence_pct > 0 AND prevalence_pct < 100",
            name="ck_epidemiology_prevalence_range",
        ),
        CheckConstraint(
            "(prevalence_low IS NULL OR prevalence_low <= prevalence_pct) "
            "AND (prevalence_high IS NULL OR prevalence_high >= prevalence_pct)",
            name="ck_epidemiology_interval_ordered",
        ),
    )


class FunnelDefault(Base):
    """A seeded funnel rate. `country_code` NULL means the indication-level global."""

    __tablename__ = "funnel_defaults"

    id: Mapped[int] = mapped_column(primary_key=True)
    indication_id: Mapped[int] = mapped_column(
        ForeignKey("indications.indication_id")
    )
    country_code: Mapped[CountryCode | None] = mapped_column(
        ForeignKey("countries.country_code")
    )
    stage: Mapped[str] = mapped_column(Text)
    value: Mapped[Rate]
    value_low: Mapped[Rate | None]
    value_high: Mapped[Rate | None]
    source: Mapped[str] = mapped_column(Text)
    confidence_tier: Mapped[ConfidenceTierCol]

    __table_args__ = (
        UniqueConstraint(
            "indication_id", "country_code", "stage", name="uq_funnel_defaults_natural"
        ),
        # Rates are fractions. A value of 45 here rather than 0.45 would inflate
        # every downstream population by two orders of magnitude.
        CheckConstraint("value > 0 AND value <= 1", name="ck_funnel_defaults_rate"),
    )


class EligibilityCriterion(Base):
    __tablename__ = "eligibility_criteria"

    criterion_id: Mapped[int] = mapped_column(primary_key=True)
    indication_id: Mapped[int] = mapped_column(
        ForeignKey("indications.indication_id")
    )
    criterion_code: Mapped[str] = mapped_column(Text)
    criterion_label: Mapped[str] = mapped_column(Text)
    criterion_type: Mapped[str] = mapped_column(Text)
    default_factor: Mapped[Rate]
    factor_low: Mapped[Rate | None]
    factor_high: Mapped[Rate | None]
    source: Mapped[str] = mapped_column(Text)
    confidence_tier: Mapped[ConfidenceTierCol]

    # Criterion codes that overlap this one and must not be multiplied with it.
    # M3 uses this to avoid compounding correlated restrictions.
    correlated_with: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    __table_args__ = (
        UniqueConstraint(
            "indication_id", "criterion_code", name="uq_eligibility_criteria_natural"
        ),
        CheckConstraint(
            "default_factor > 0 AND default_factor <= 1",
            name="ck_eligibility_criteria_factor",
        ),
    )


class Drug(Base):
    __tablename__ = "drugs"

    drug_id: Mapped[int] = mapped_column(primary_key=True)
    drug_name: Mapped[str] = mapped_column(Text)
    generic_name: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    drug_class: Mapped[str | None] = mapped_column(Text)
    route: Mapped[str | None] = mapped_column(Text)
    indication_id: Mapped[int | None] = mapped_column(
        ForeignKey("indications.indication_id")
    )
    is_comparator: Mapped[bool] = mapped_column(Boolean, default=True)

    regimens: Mapped[list[DrugRegimen]] = relationship(back_populates="drug")
    prices: Mapped[list[DrugPrice]] = relationship(back_populates="drug")

    __table_args__ = (
        UniqueConstraint("drug_name", name="uq_drugs_name"),
    )


class DrugRegimen(Base):
    """Dose and administration schedule. Turns a unit price into an annual cost."""

    __tablename__ = "drug_regimens"

    regimen_id: Mapped[int] = mapped_column(primary_key=True)
    drug_id: Mapped[int] = mapped_column(ForeignKey("drugs.drug_id"))
    dose_amount: Mapped[Quantity]
    dose_unit: Mapped[str] = mapped_column(Text)
    units_per_admin: Mapped[Quantity]
    admins_per_year: Mapped[Quantity]
    wastage_pct: Mapped[Rate] = mapped_column(Numeric(5, 4), default=0)
    persistence_12m: Mapped[Rate] = mapped_column(Numeric(5, 4), default=1)
    source: Mapped[str] = mapped_column(Text)
    confidence_tier: Mapped[ConfidenceTierCol]

    drug: Mapped[Drug] = relationship(back_populates="regimens")

    __table_args__ = (
        UniqueConstraint("drug_id", name="uq_drug_regimens_drug"),
        CheckConstraint(
            "wastage_pct >= 0 AND wastage_pct < 1", name="ck_drug_regimens_wastage"
        ),
        CheckConstraint(
            "persistence_12m > 0 AND persistence_12m <= 1",
            name="ck_drug_regimens_persistence",
        ),
    )


class DrugPrice(Base):
    """A price in local currency, with the basis it was struck on.

    `price_local` is always in `currency_code`, which must match the market's
    currency. `annual_cost_usd` is the derived convenience value; FX used to
    derive it is snapshotted into the run, never looked up live.
    """

    __tablename__ = "drug_prices"

    price_id: Mapped[int] = mapped_column(primary_key=True)
    drug_id: Mapped[int] = mapped_column(ForeignKey("drugs.drug_id"))
    country_code: Mapped[CountryCode] = mapped_column(
        ForeignKey("countries.country_code")
    )
    price_local: Mapped[Quantity]
    currency_code: Mapped[CurrencyCode]
    price_basis: Mapped[str] = mapped_column(Text)
    annual_cost_usd: Mapped[Quantity | None]
    gross_to_net_pct: Mapped[Rate | None] = mapped_column(Numeric(5, 4))
    effective_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    confidence_tier: Mapped[ConfidenceTierCol]

    drug: Mapped[Drug] = relationship(back_populates="prices")

    __table_args__ = (
        UniqueConstraint(
            "drug_id", "country_code", "price_basis", name="uq_drug_prices_natural"
        ),
        CheckConstraint("price_local > 0", name="ck_drug_prices_positive"),
        CheckConstraint(
            "gross_to_net_pct IS NULL "
            "OR (gross_to_net_pct > 0 AND gross_to_net_pct <= 1)",
            name="ck_drug_prices_gross_to_net",
        ),
        # A stated net price must say what assumption produced it.
        CheckConstraint(
            "price_basis <> 'estimated_net' OR gross_to_net_pct IS NOT NULL",
            name="ck_drug_prices_net_requires_ratio",
        ),
    )


class FxRate(Base):
    """Units of `currency_code` per one USD. USD itself is stored as 1.0.

    The identity row is not redundant: it lets M7 pivot every conversion through
    USD without a special case for the base currency.
    """

    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency_code: Mapped[CurrencyCode]
    rate_per_usd: Mapped[Quantity]
    fetched_date: Mapped[date] = mapped_column(Date)

    __table_args__ = (
        UniqueConstraint("currency_code", "fetched_date", name="uq_fx_rates_natural"),
        CheckConstraint("rate_per_usd > 0", name="ck_fx_rates_positive"),
        Index("idx_fx_rates_lookup", "currency_code", "fetched_date"),
    )
