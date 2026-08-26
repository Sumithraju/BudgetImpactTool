"""Adverse-event profile persistence — M13."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models.safety import AdverseEvent, AdverseEventCost, DrugAdverseEvent
from .base import BaseRepository


class SafetyRepository(BaseRepository[DrugAdverseEvent]):
    model = DrugAdverseEvent

    def load_incidences(
        self, drug_ids: Sequence[int],
    ) -> dict[int, list[DrugAdverseEvent]]:
        """`drug_id -> [incidence, ...]`, one query for the whole matrix.

        A calculation touches every therapy in the mix across every market;
        one query per therapy would be the N+1 the standards call a defect.
        """
        if not drug_ids:
            return {}
        rows = self._session.scalars(
            select(DrugAdverseEvent).where(DrugAdverseEvent.drug_id.in_(drug_ids))
        ).all()

        out: dict[int, list[DrugAdverseEvent]] = {}
        for row in rows:
            out.setdefault(row.drug_id, []).append(row)
        return out

    def load_unit_costs(
        self, country_codes: Sequence[str],
    ) -> dict[tuple[str, str], AdverseEventCost]:
        """`(ae_code, country_code) -> cost`, for every market at once."""
        if not country_codes:
            return {}
        rows = self._session.scalars(
            select(AdverseEventCost)
            .where(AdverseEventCost.country_code.in_(country_codes))
            .options(selectinload(AdverseEventCost.event))
        ).all()
        return {(r.ae_code, str(r.country_code)): r for r in rows}

    def list_events(self) -> Sequence[AdverseEvent]:
        return self._session.scalars(
            select(AdverseEvent).order_by(AdverseEvent.ae_code)
        ).all()
