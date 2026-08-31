"""SQLAlchemy ORM models.

Importing this package registers every table on `Base.metadata`, which is what
Alembic autogenerate reflects against. A model that is not imported here is
invisible to migrations.
"""

from __future__ import annotations

from .base import Base
from .comparator import ComparatorApproval, ComparatorAsset
from .evidence import EvidenceRecord
from .knowledge import GuidelineChunk, GuidelineDocument
from .outcomes import (
    CountryHealthIndicator,
    DiseaseSubgroup,
    EventCost,
    ResponseProfile,
    SubgroupCountryRate,
    SubgroupEventRate,
    TreatmentEffect,
)
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
from .safety import AdverseEvent, AdverseEventCost, DrugAdverseEvent
from .scenario import ModelRun, Scenario, ScenarioOverride
from .staging import StagingExtract

__all__ = [
    "AdverseEvent",
    "AdverseEventCost",
    "Base",
    "ComparatorApproval",
    "ComparatorAsset",
    "Country",
    "CountryEconomics",
    "CountryHealthIndicator",
    "DiseaseSubgroup",
    "Drug",
    "DrugAdverseEvent",
    "DrugPrice",
    "DrugRegimen",
    "EligibilityCriterion",
    "Epidemiology",
    "EventCost",
    "EvidenceRecord",
    "FunnelDefault",
    "FxRate",
    "GuidelineChunk",
    "GuidelineDocument",
    "Indication",
    "ModelRun",
    "ResponseProfile",
    "Scenario",
    "ScenarioOverride",
    "StagingExtract",
    "SubgroupCountryRate",
    "SubgroupEventRate",
    "TreatmentEffect",
]
