"""Comparator registry ORM models — M12, ARCHITECTURE.md §8.4.

`comparator_assets` is the single drug–target–market record. Three groups of
columns, distinguished by who writes them: mechanistic columns come from M11's
retrieval, commercial columns from a curator, and the economic ones live in
`drugs`/`drug_regimens`/`drug_prices` and are linked by `drug_id`.

`drug_id` being null is the whole point of the table: it is the flag that says
this molecule is known about but cannot yet enter a calculation.
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
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ConfidenceTierCol, CountryCode, Rate
from .reference import Drug


class ComparatorAsset(Base):
    """One molecule, in one indication, as far as this system knows it."""

    __tablename__ = "comparator_assets"

    asset_id: Mapped[int] = mapped_column(primary_key=True)

    # --- identity -------------------------------------------------------
    source_id: Mapped[str] = mapped_column(Text)     # ChEMBL id, the cross-source key
    asset_name: Mapped[str] = mapped_column(Text)
    indication_id: Mapped[int] = mapped_column(ForeignKey("indications.indication_id"))

    # --- mechanistic, written by M11 retrieval --------------------------
    target_symbol: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)          # Ensembl gene id
    mechanism_of_action: Mapped[str | None] = mapped_column(Text)
    action_type: Mapped[str | None] = mapped_column(Text)
    pathway_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}",
    )
    drug_type: Mapped[str | None] = mapped_column(Text)
    max_clinical_stage: Mapped[str] = mapped_column(Text)
    competitor_class: Mapped[str] = mapped_column(Text)
    relevance: Mapped[float] = mapped_column(Numeric(6, 4))
    rationale: Mapped[str] = mapped_column(Text)

    # --- commercial, written by a curator -------------------------------
    brand_name: Mapped[str | None] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    route: Mapped[str | None] = mapped_column(Text)
    line_of_therapy: Mapped[str | None] = mapped_column(Text)

    # --- pipeline, consumed by M14 --------------------------------------
    sponsor: Mapped[str | None] = mapped_column(Text)
    primary_completion: Mapped[date | None] = mapped_column(Date)
    expected_entry_year: Mapped[int | None] = mapped_column(SmallInteger)
    assumed_terminal_pct: Mapped[Rate | None] = mapped_column(Numeric(5, 4))

    # --- linkage and provenance -----------------------------------------
    is_new_asset: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Null until promoted. Nothing without one can enter a calculation.
    drug_id: Mapped[int | None] = mapped_column(ForeignKey("drugs.drug_id"))
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    confidence_tier: Mapped[ConfidenceTierCol] = mapped_column(default="B")

    drug: Mapped[Drug | None] = relationship()
    approvals: Mapped[list[ComparatorApproval]] = relationship(
        back_populates="asset", cascade="all, delete-orphan",
    )

    __table_args__ = (
        # One record per molecule per indication. The same molecule in two
        # indications is two records: its line of therapy, comparator set and
        # relevance all differ between them (M12 section 5.2).
        UniqueConstraint("source_id", "indication_id", name="uq_comparator_assets_natural"),
        CheckConstraint(
            "relevance >= 0 AND relevance <= 1", name="ck_comparator_assets_relevance",
        ),
        CheckConstraint(
            "assumed_terminal_pct IS NULL "
            "OR (assumed_terminal_pct > 0 AND assumed_terminal_pct < 1)",
            name="ck_comparator_assets_terminal_share",
        ),
    )

    @property
    def is_promoted(self) -> bool:
        return self.drug_id is not None


class ComparatorApproval(Base):
    """Where a comparator is approved, and whether it is reimbursed there.

    A therapy not approved in a market cannot be in that market's
    world-without. That inference is deliberately not enforced (M12 section
    12) — coverage is too thin to make it a rule — but it is recorded so the
    curator can act on it.
    """

    __tablename__ = "comparator_approvals"

    approval_id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("comparator_assets.asset_id", ondelete="CASCADE"),
    )
    country_code: Mapped[CountryCode] = mapped_column(
        ForeignKey("countries.country_code"),
    )
    approval_year: Mapped[int | None] = mapped_column(SmallInteger)
    is_reimbursed: Mapped[bool | None] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(Text)
    confidence_tier: Mapped[ConfidenceTierCol] = mapped_column(default="B")

    asset: Mapped[ComparatorAsset] = relationship(back_populates="approvals")

    __table_args__ = (
        UniqueConstraint("asset_id", "country_code", name="uq_comparator_approvals_natural"),
    )


__all__ = ["ComparatorApproval", "ComparatorAsset"]
