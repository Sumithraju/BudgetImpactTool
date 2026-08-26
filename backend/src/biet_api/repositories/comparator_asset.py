"""Persistence for the comparator registry — M12.

Queries only. Whether an asset may be promoted, and what promotion writes,
are decisions and live in the service.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models.comparator import ComparatorAsset
from ..models.reference import Drug, DrugPrice, DrugRegimen
from .base import BaseRepository


class ComparatorAssetRepository(BaseRepository[ComparatorAsset]):
    model = ComparatorAsset

    def get_by_natural_key(self, source_id: str, indication_id: int) -> ComparatorAsset | None:
        """One record per molecule per indication (M12 section 5.2)."""
        stmt = (
            select(ComparatorAsset)
            .where(ComparatorAsset.source_id == source_id)
            .where(ComparatorAsset.indication_id == indication_id)
            .options(selectinload(ComparatorAsset.approvals))
        )
        return self._session.scalars(stmt).one_or_none()

    def list_for_indication(
        self, indication_id: int, *, competitor_class: str | None = None,
    ) -> Sequence[ComparatorAsset]:
        stmt = (
            select(ComparatorAsset)
            .where(ComparatorAsset.indication_id == indication_id)
            # selectinload rather than a lazy load per row: the registry is
            # always rendered as a list, and one query per asset for its
            # approvals is the N+1 the standards call a defect.
            .options(selectinload(ComparatorAsset.approvals))
            .order_by(ComparatorAsset.relevance.desc(), ComparatorAsset.asset_name)
        )
        if competitor_class is not None:
            stmt = stmt.where(ComparatorAsset.competitor_class == competitor_class)
        return self._session.scalars(stmt).all()

    def list_by_ids(self, asset_ids: Sequence[int]) -> Sequence[ComparatorAsset]:
        if not asset_ids:
            return []
        stmt = select(ComparatorAsset).where(ComparatorAsset.asset_id.in_(asset_ids))
        return self._session.scalars(stmt).all()

    # ----------------------------------------------------------------- drugs side

    def get_drug_by_name(self, name: str) -> Drug | None:
        """Case-insensitive match against either name a drug row carries.

        Promotion links to an existing row rather than creating a second:
        `uq_drugs_name` would reject the duplicate anyway, and failing on a
        unique constraint is not an acceptable way to express a business rule
        (M12 section 5.3).
        """
        key = name.strip().lower()
        stmt = select(Drug).where(
            (Drug.drug_name.ilike(key)) | (Drug.generic_name.ilike(key))
        )
        return self._session.scalars(stmt).first()

    def get_regimen(self, drug_id: int) -> DrugRegimen | None:
        stmt = select(DrugRegimen).where(DrugRegimen.drug_id == drug_id)
        return self._session.scalars(stmt).one_or_none()

    def list_prices(self, drug_id: int) -> Sequence[DrugPrice]:
        stmt = select(DrugPrice).where(DrugPrice.drug_id == drug_id)
        return self._session.scalars(stmt).all()

    def priced_markets(self, drug_id: int) -> set[str]:
        stmt = select(DrugPrice.country_code).where(DrugPrice.drug_id == drug_id)
        return {str(code) for code in self._session.scalars(stmt).all()}
