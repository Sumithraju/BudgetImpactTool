"""Adverse-event catalogue and profiles — M13, ARCHITECTURE.md §8.4.

Two catalogues and one join. The event vocabulary and its per-market
management cost are reference data; incidence is a property of a *therapy*
observed in a specific trial over a specific window, and the window is stored
because an incidence without one cannot be annualised (§5.10).

`confidence_tier` has no default on `drug_adverse_events` specifically. An
adverse-event incidence is the value in this system most likely to be repeated
as fact, so it cannot be written without one.
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ConfidenceTierCol, CountryCode, CurrencyCode, Quantity, Rate


class AdverseEvent(Base):
    """The event vocabulary. Shared across therapies and markets."""

    __tablename__ = "adverse_events"

    ae_code: Mapped[str] = mapped_column(Text, primary_key=True)
    ae_label: Mapped[str] = mapped_column(Text)
    is_serious: Mapped[bool] = mapped_column(Boolean, default=False)
    meddra_pt: Mapped[str | None] = mapped_column(Text)

    costs: Mapped[list[AdverseEventCost]] = relationship(back_populates="event")


class AdverseEventCost(Base):
    """What managing one occurrence costs, in one market."""

    __tablename__ = "adverse_event_costs"

    ae_cost_id: Mapped[int] = mapped_column(primary_key=True)
    ae_code: Mapped[str] = mapped_column(ForeignKey("adverse_events.ae_code"))
    country_code: Mapped[CountryCode] = mapped_column(
        ForeignKey("countries.country_code")
    )
    unit_cost_local: Mapped[Quantity]
    currency_code: Mapped[CurrencyCode]
    cost_year: Mapped[int | None] = mapped_column(SmallInteger)
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    confidence_tier: Mapped[ConfidenceTierCol] = mapped_column(default="C")

    event: Mapped[AdverseEvent] = relationship(back_populates="costs")

    __table_args__ = (
        UniqueConstraint("ae_code", "country_code", name="uq_ae_costs_natural"),
        CheckConstraint("unit_cost_local >= 0", name="ck_ae_costs_non_negative"),
    )


class DrugAdverseEvent(Base):
    """One therapy's observed rate for one event, and where it was observed."""

    __tablename__ = "drug_adverse_events"

    dae_id: Mapped[int] = mapped_column(primary_key=True)
    drug_id: Mapped[int] = mapped_column(
        ForeignKey("drugs.drug_id", ondelete="CASCADE")
    )
    ae_code: Mapped[str] = mapped_column(ForeignKey("adverse_events.ae_code"))
    incidence: Mapped[Rate] = mapped_column(Numeric(6, 5))
    #: Null means the source already reports an annual rate. Anything else is
    #: the window the incidence was observed over, which is what makes
    #: annualisation possible at all.
    exposure_weeks: Mapped[int | None] = mapped_column(SmallInteger)
    population: Mapped[str | None] = mapped_column(Text)
    evidence_type: Mapped[str] = mapped_column(Text)     # trial | label | literature
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    vintage_year: Mapped[int | None] = mapped_column(SmallInteger)
    #: No default, deliberately. See the module docstring.
    confidence_tier: Mapped[ConfidenceTierCol]

    __table_args__ = (
        UniqueConstraint("drug_id", "ae_code", name="uq_drug_adverse_events_natural"),
        CheckConstraint(
            "incidence >= 0 AND incidence <= 1", name="ck_drug_adverse_events_incidence",
        ),
        CheckConstraint(
            "exposure_weeks IS NULL OR exposure_weeks > 0",
            name="ck_drug_adverse_events_exposure",
        ),
    )


__all__ = ["AdverseEvent", "AdverseEventCost", "DrugAdverseEvent"]
