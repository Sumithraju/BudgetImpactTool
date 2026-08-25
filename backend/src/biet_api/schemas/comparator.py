"""API schemas for the comparator registry — M12 section 4.

Separate from the ORM models and from the engine's contracts, per the
three-families rule (biet-backend skill section 3). These are the HTTP shape;
nothing here is persisted directly and nothing here reaches the engine.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from ..constants.comparator import CompetitorClass, LineOfTherapy


class MarketApprovalIn(BaseModel):
    country_code: str = Field(min_length=3, max_length=3)
    approval_year: int | None = Field(default=None, ge=1900, le=2100)
    is_reimbursed: bool | None = None
    source: str = Field(min_length=1)
    confidence_tier: str = Field(default="B", min_length=1, max_length=1)


class AssetIntake(BaseModel):
    """The new asset, or a discovered comparator being registered.

    Only indication and target are required. Everything a public source can
    answer is pre-filled by M11 and arrives here already populated; what no
    source can answer — expected launch year, target markets, line of
    therapy — is entered directly and is tier C or D by construction
    (M12 section 5.1).
    """

    source_id: str = Field(min_length=1, max_length=64)
    asset_name: str = Field(min_length=1, max_length=200)
    indication_id: int
    target_symbol: str = Field(min_length=1, max_length=40)

    target_id: str | None = None
    mechanism_of_action: str | None = None
    action_type: str | None = None
    pathway_ids: list[str] = Field(default_factory=list)
    drug_type: str | None = None
    max_clinical_stage: str = "UNKNOWN"
    competitor_class: CompetitorClass = CompetitorClass.THERAPEUTIC
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = "registered by hand"

    brand_name: str | None = None
    manufacturer: str | None = None
    route: str | None = None
    line_of_therapy: LineOfTherapy | None = None

    sponsor: str | None = None
    primary_completion: date | None = None
    expected_entry_year: int | None = Field(default=None, ge=1, le=20)
    assumed_terminal_pct: float | None = Field(default=None, gt=0.0, lt=1.0)

    is_new_asset: bool = False
    source: str = Field(default="user", min_length=1)
    source_url: str | None = None
    confidence_tier: str = Field(default="C", min_length=1, max_length=1)
    approvals: list[MarketApprovalIn] = Field(default_factory=list)


class RegimenIn(BaseModel):
    """Dose and schedule. Turns a unit price into an annual cost."""

    dose_amount: float = Field(gt=0)
    dose_unit: str = Field(min_length=1, max_length=20)
    units_per_admin: float = Field(gt=0)
    admins_per_year: float = Field(gt=0)
    wastage_pct: float = Field(default=0.0, ge=0.0, lt=1.0)
    persistence_12m: float = Field(default=1.0, gt=0.0, le=1.0)
    source: str = Field(min_length=1)
    confidence_tier: str = Field(default="C", min_length=1, max_length=1)


class PriceIn(BaseModel):
    country_code: str = Field(min_length=3, max_length=3)
    price_local: float = Field(gt=0)
    currency_code: str = Field(min_length=3, max_length=3)
    price_basis: str = Field(min_length=1)
    gross_to_net_pct: float | None = Field(default=None, gt=0.0, le=1.0)
    effective_date: date | None = None
    source: str = Field(min_length=1)
    source_url: str | None = None
    confidence_tier: str = Field(default="C", min_length=1, max_length=1)


class PromotionRequest(BaseModel):
    """What a discovered molecule needs before it can be a comparator.

    Both halves are mandatory. A comparator with a regimen and no price is
    not usable, and promotion is all-or-nothing (M12 section 5.3).
    """

    regimen: RegimenIn
    prices: list[PriceIn] = Field(min_length=1)
    company: str | None = None
    drug_class: str | None = None


class MarketApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    country_code: str
    approval_year: int | None
    is_reimbursed: bool | None
    source: str
    confidence_tier: str


class RegisteredAsset(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: int
    source_id: str
    asset_name: str
    indication_id: int
    target_symbol: str
    mechanism_of_action: str | None
    action_type: str | None
    pathway_ids: list[str]
    max_clinical_stage: str
    competitor_class: str
    relevance: float
    rationale: str
    brand_name: str | None
    manufacturer: str | None
    line_of_therapy: str | None
    sponsor: str | None
    expected_entry_year: int | None
    is_new_asset: bool
    drug_id: int | None
    is_promoted: bool
    #: What still stands between this asset and a calculation, named per
    #: market so the interface can say "needs a German price" rather than
    #: "not ready" (M12 section 5.4).
    missing_for_promotion: list[str]
    source: str
    confidence_tier: str
    approvals: list[MarketApprovalRead]
