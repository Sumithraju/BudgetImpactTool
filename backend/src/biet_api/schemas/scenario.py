"""API request/response contracts — M1 section 4.

Deliberately separate from the ORM models and from `biet_engine`'s frozen
input models (the backend standards, section 3). The three families answer
different questions: what a client may send, what is stored, and what the
engine consumes. Sharing one model across all three couples the HTTP
contract to the database schema, and every later change then breaks both.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MIN_LAUNCH_YEAR = 2026
MAX_LAUNCH_YEAR = 2040


class OverrideItem(BaseModel):
    """One assumption the user has replaced.

    `country_code` None applies the override to every market in the
    scenario, but is still beaten by one naming a market explicitly.
    """

    model_config = ConfigDict(frozen=True)

    country_code: str | None = None
    parameter_path: str
    value: float | int | str | bool | list[float]
    note: str | None = None


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    indication_id: int
    asset_name: str = Field(min_length=1, max_length=200)
    asset_class: str | None = None
    development_stage: str | None = None
    launch_year: int = Field(ge=MIN_LAUNCH_YEAR, le=MAX_LAUNCH_YEAR)
    horizon_years: int = Field(default=3, ge=1, le=5)
    reporting_currency: str = Field(default="USD", min_length=3, max_length=3)
    country_codes: list[str] = Field(min_length=1)
    #: M17. Whose budget this lands on. Defaulted rather than required, because
    #: every scenario written before perspectives existed was in effect a
    #: health-system one — the denominator was the national population because
    #: there was no other.
    perspective: Literal["insurer", "employer", "government", "health_system"] = (
        "health_system"
    )
    #: Covered lives, for a perspective narrower than the nation. None means
    #: "the whole market", which is correct for a health system and an
    #: assumption for anyone else — the run says which.
    covered_population: int | None = Field(default=None, gt=0)
    #: M18. The clinically distinct populations this run covers. Empty means
    #: the whole diagnosed population as one undifferentiated segment.
    subgroup_codes: list[str] = Field(default_factory=list)
    overrides: list[OverrideItem] = Field(default_factory=list)


class ScenarioUpdate(BaseModel):
    """Partial update. Every field optional; unset fields are left alone —
    which is why this cannot just reuse `ScenarioCreate` with defaults."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    asset_name: str | None = Field(default=None, min_length=1, max_length=200)
    asset_class: str | None = None
    development_stage: str | None = None
    launch_year: int | None = Field(default=None, ge=MIN_LAUNCH_YEAR, le=MAX_LAUNCH_YEAR)
    horizon_years: int | None = Field(default=None, ge=1, le=5)
    reporting_currency: str | None = Field(default=None, min_length=3, max_length=3)
    country_codes: list[str] | None = Field(default=None, min_length=1)
    perspective: (
        Literal["insurer", "employer", "government", "health_system"] | None
    ) = None
    covered_population: int | None = Field(default=None, gt=0)
    subgroup_codes: list[str] | None = None


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scenario_id: uuid.UUID
    name: str
    description: str | None
    indication_id: int
    asset_name: str
    asset_class: str | None
    development_stage: str | None
    launch_year: int
    horizon_years: int
    reporting_currency: str
    country_codes: list[str]
    perspective: str
    covered_population: int | None
    subgroup_codes: list[str]
    parent_scenario_id: uuid.UUID | None
    is_baseline: bool
    is_archived: bool
    overrides: list[OverrideItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ScenarioClone(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    override_patch: list[OverrideItem] = Field(default_factory=list)


class OverrideReplace(BaseModel):
    """`PUT /overrides` replaces the whole set rather than merging — a merge
    has no way to express "remove this override"."""

    overrides: list[OverrideItem]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


# --------------------------------------------------------------------------- errors


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None
    context: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """One envelope for every non-2xx response (the backend standards, section 8.3)."""

    error: ErrorDetail
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: str
