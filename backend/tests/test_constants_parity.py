"""biet_engine.constants mirrors part of biet_api.constants.domain, because
the engine cannot import biet_api (test_layering.py enforces that). This test
is the guard against the two drifting apart silently — see the docstring on
biet_engine/constants.py. Only this test file is allowed to import both.
"""

from __future__ import annotations

from biet_api.constants.domain import CriterionType as ApiCriterionType
from biet_api.constants.domain import FunnelStage as ApiFunnelStage
from biet_api.constants.domain import PriceBasis as ApiPriceBasis
from biet_engine.constants import CriterionType as EngineCriterionType
from biet_engine.constants import FunnelStage as EngineFunnelStage
from biet_engine.constants import PriceBasis as EnginePriceBasis


def _members(enum_cls: type) -> set[str]:
    return {member.value for member in enum_cls}


def test_funnel_stage_members_match() -> None:
    assert _members(EngineFunnelStage) == _members(ApiFunnelStage)


def test_criterion_type_members_match() -> None:
    assert _members(EngineCriterionType) == _members(ApiCriterionType)


def test_price_basis_members_match() -> None:
    assert _members(EnginePriceBasis) == _members(ApiPriceBasis)
