"""Scenario, override and run persistence — M1 sections 5.4 to 5.6."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models.scenario import ModelRun, Scenario, ScenarioOverride
from .base import BaseRepository


class ScenarioRepository(BaseRepository[Scenario]):
    model = Scenario

    def get_with_overrides(self, scenario_id: uuid.UUID) -> Scenario | None:
        """One query, overrides eagerly loaded — a lazy load per override
        would be the N+1 the standards forbid."""
        return self._session.scalars(
            select(Scenario)
            .where(Scenario.scenario_id == scenario_id)
            .options(selectinload(Scenario.overrides))
        ).one_or_none()

    def list_scenarios(
        self,
        *,
        indication_id: int | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Scenario]:
        stmt = select(Scenario).options(selectinload(Scenario.overrides))
        if indication_id is not None:
            stmt = stmt.where(Scenario.indication_id == indication_id)
        if not include_archived:
            stmt = stmt.where(Scenario.is_archived.is_(False))
        stmt = stmt.order_by(Scenario.created_at.desc()).limit(limit).offset(offset)
        return self._session.scalars(stmt).all()

    def count_scenarios(
        self, *, indication_id: int | None = None, include_archived: bool = False,
    ) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Scenario)
        if indication_id is not None:
            stmt = stmt.where(Scenario.indication_id == indication_id)
        if not include_archived:
            stmt = stmt.where(Scenario.is_archived.is_(False))
        return self._session.scalar(stmt) or 0

    def get_baseline(self, indication_id: int) -> Scenario | None:
        """The current baseline holder for an indication, if any.

        At most one exists (M1 section 5.5); `one_or_none` rather than
        `first` so a second holder surfaces as an error instead of being
        silently picked between.
        """
        return self._session.scalars(
            select(Scenario)
            .where(Scenario.indication_id == indication_id)
            .where(Scenario.is_baseline.is_(True))
        ).one_or_none()


class OverrideRepository(BaseRepository[ScenarioOverride]):
    model = ScenarioOverride

    def replace_for(
        self, scenario_id: uuid.UUID, overrides: Sequence[ScenarioOverride],
    ) -> None:
        """Swap the whole override set — `PUT /overrides` replaces, it does
        not merge (M1 section 8)."""
        existing = self._session.scalars(
            select(ScenarioOverride).where(ScenarioOverride.scenario_id == scenario_id)
        ).all()
        for row in existing:
            self._session.delete(row)
        self._session.flush()
        for override in overrides:
            self._session.add(override)


class RunRepository(BaseRepository[ModelRun]):
    """Append-only. `model_runs` rows are never updated (M1 section 5.6)."""

    model = ModelRun

    def list_for_scenario(
        self, scenario_id: uuid.UUID, *, limit: int = 20,
    ) -> Sequence[ModelRun]:
        return self._session.scalars(
            select(ModelRun)
            .where(ModelRun.scenario_id == scenario_id)
            .order_by(ModelRun.created_at.desc())
            .limit(limit)
        ).all()

    def get_latest_forward(self, scenario_id: uuid.UUID) -> ModelRun | None:
        return self._session.scalars(
            select(ModelRun)
            .where(ModelRun.scenario_id == scenario_id)
            .where(ModelRun.run_type == "forward")
            .order_by(ModelRun.created_at.desc())
            .limit(1)
        ).one_or_none()
