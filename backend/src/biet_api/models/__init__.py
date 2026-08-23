"""SQLAlchemy ORM models.

Importing this package registers every table on `Base.metadata`, which is what
Alembic autogenerate reflects against. A model that is not imported here is
invisible to migrations.
"""

from __future__ import annotations

from .base import Base
from .knowledge import GuidelineChunk, GuidelineDocument
from .reference import (
    Country,
    CountryEconomics,
    Drug,
    DrugPrice,
    DrugRegimen,
    EligibilityCriterion,
    Epidemiology,
    FunnelDefault,
    FxRate,
    Indication,
)
from .scenario import ModelRun, Scenario, ScenarioOverride
from .staging import StagingExtract

__all__ = [
    "Base",
    "Country",
    "CountryEconomics",
    "Drug",
    "DrugPrice",
    "DrugRegimen",
    "EligibilityCriterion",
    "Epidemiology",
    "FunnelDefault",
    "FxRate",
    "GuidelineChunk",
    "GuidelineDocument",
    "Indication",
    "ModelRun",
    "Scenario",
    "ScenarioOverride",
    "StagingExtract",
]
