"""Scenario and run data — ARCHITECTURE.md section 8.2.

`model_runs` is append-only. `input_snapshot` holds every resolved value the
engine consumed, so replaying it through the recorded `engine_version` reproduces
the result exactly. That is what makes a run auditable (non-negotiable 9).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..constants.domain import RunType
from .base import Base, CountryCode, CurrencyCode

MIN_HORIZON_YEARS = 1
MAX_HORIZON_YEARS = 5


class Scenario(Base):
    __tablename__ = "scenarios"

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    indication_id: Mapped[int] = mapped_column(
        ForeignKey("indications.indication_id")
    )
    asset_name: Mapped[str] = mapped_column(Text)
    asset_class: Mapped[str | None] = mapped_column(Text)
    development_stage: Mapped[str | None] = mapped_column(Text)

    # Calendar year of launch. Engine input is launch-relative: internally year 1
    # is the launch year and the calendar year is derived only for display
    # (non-negotiable 7).
    launch_year: Mapped[int] = mapped_column(SmallInteger)
    horizon_years: Mapped[int] = mapped_column(SmallInteger, default=3)
    reporting_currency: Mapped[CurrencyCode] = mapped_column(default="USD")
    country_codes: Mapped[list[str]] = mapped_column(ARRAY(CHAR(3)))

    parent_scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.scenario_id")
    )
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)

    # Soft delete. M1 section 6: a scenario with runs is archived, never
    # hard-deleted, because `model_runs` rows reference it and a run whose
    # parent scenario vanished is no longer reproducible — which is the whole
    # point of storing it (non-negotiable 9). Archived scenarios stay
    # readable (section 12).
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    overrides: Mapped[list[ScenarioOverride]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            f"horizon_years BETWEEN {MIN_HORIZON_YEARS} AND {MAX_HORIZON_YEARS}",
            name="ck_scenarios_horizon_range",
        ),
        CheckConstraint(
            "cardinality(country_codes) > 0", name="ck_scenarios_has_market"
        ),
    )


class ScenarioOverride(Base):
    """A user-supplied value replacing a seeded default, level 3 of section 7.3.

    `country_code` NULL applies the override to every market in the scenario.
    """

    __tablename__ = "scenario_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scenarios.scenario_id", ondelete="CASCADE"),
    )
    country_code: Mapped[CountryCode | None]
    parameter_path: Mapped[str] = mapped_column(Text)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(Text)

    scenario: Mapped[Scenario] = relationship(back_populates="overrides")

    __table_args__ = (
        UniqueConstraint(
            "scenario_id",
            "country_code",
            "parameter_path",
            name="uq_scenario_overrides_natural",
        ),
    )


class ModelRun(Base):
    """Append-only. Rows are never updated."""

    __tablename__ = "model_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.scenario_id")
    )
    engine_version: Mapped[str] = mapped_column(Text)
    run_type: Mapped[str] = mapped_column(Text)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    fx_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    results: Mapped[dict[str, Any]] = mapped_column(JSONB)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_model_runs_scenario", "scenario_id", created_at.desc()),
        CheckConstraint(
            "run_type IN ("
            + ", ".join(f"'{member.value}'" for member in RunType)
            + ")",
            name="ck_model_runs_type",
        ),
    )
