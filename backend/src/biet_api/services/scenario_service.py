"""Scenario lifecycle — M1 sections 5.4 to 5.7.

Services own decisions and transaction boundaries; repositories own queries.
Every override is validated against the closed vocabulary before it reaches
storage, so an invalid one fails at the boundary rather than surfacing later
as an unresolvable parameter.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from ..exceptions import ConflictError, EntityNotFoundError, ValidationError
from ..models.reference import Indication
from ..models.scenario import ModelRun, Scenario, ScenarioOverride
from ..repositories.outcomes import OutcomesRepository
from ..repositories.reference import ReferenceRepository
from ..repositories.scenario import OverrideRepository, RunRepository, ScenarioRepository
from ..schemas.scenario import OverrideItem, ScenarioCreate, ScenarioUpdate
from .override_validator import validate_override

#: M1 section 5.7 — comparison takes 2 to 4 scenarios. Below two there is
#: nothing to compare; above four the side-by-side stops being readable.
MIN_COMPARE = 2
MAX_COMPARE = 4


class ScenarioService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._scenarios = ScenarioRepository(session)
        self._overrides = OverrideRepository(session)
        self._runs = RunRepository(session)
        self._reference = ReferenceRepository(session)

    # ----------------------------------------------------------------- reads

    def require(self, scenario_id: uuid.UUID) -> Scenario:
        scenario = self._scenarios.get_with_overrides(scenario_id)
        if scenario is None:
            raise EntityNotFoundError(
                f"no scenario {scenario_id}", scenario_id=str(scenario_id),
            )
        return scenario

    def list_scenarios(
        self,
        *,
        indication_id: int | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Scenario], int]:
        return (
            self._scenarios.list_scenarios(
                indication_id=indication_id, include_archived=include_archived,
                limit=limit, offset=offset,
            ),
            self._scenarios.count_scenarios(
                indication_id=indication_id, include_archived=include_archived,
            ),
        )

    # ----------------------------------------------------------------- writes

    def create(self, payload: ScenarioCreate) -> Scenario:
        self._validate_definition(
            payload.indication_id, payload.country_codes, payload.reporting_currency,
            payload.subgroup_codes,
        )
        for item in payload.overrides:
            validate_override(
                item.parameter_path, item.value, horizon_years=payload.horizon_years,
            )
        self._validate_override_identifiers(
            payload.indication_id, [i.parameter_path for i in payload.overrides],
        )

        scenario = Scenario(
            name=payload.name,
            description=payload.description,
            indication_id=payload.indication_id,
            asset_name=payload.asset_name,
            asset_class=payload.asset_class,
            development_stage=payload.development_stage,
            launch_year=payload.launch_year,
            horizon_years=payload.horizon_years,
            reporting_currency=payload.reporting_currency,
            country_codes=list(payload.country_codes),
            perspective=payload.perspective,
            covered_population=payload.covered_population,
            subgroup_codes=list(payload.subgroup_codes),
        )
        self._scenarios.add(scenario)
        self._session.flush()

        self._write_overrides(scenario.scenario_id, payload.overrides)
        self._session.flush()
        return self.require(scenario.scenario_id)

    def update(self, scenario_id: uuid.UUID, payload: ScenarioUpdate) -> Scenario:
        scenario = self.require(scenario_id)
        changes = payload.model_dump(exclude_unset=True)

        if "country_codes" in changes or "reporting_currency" in changes:
            self._validate_definition(
                scenario.indication_id,
                changes.get("country_codes", scenario.country_codes),
                changes.get("reporting_currency", scenario.reporting_currency),
                changes.get("subgroup_codes", scenario.subgroup_codes),
            )

        for field, value in changes.items():
            setattr(scenario, field, value)
        self._session.flush()
        return self.require(scenario_id)

    def replace_overrides(
        self, scenario_id: uuid.UUID, overrides: Sequence[OverrideItem],
    ) -> Scenario:
        scenario = self.require(scenario_id)
        for item in overrides:
            validate_override(
                item.parameter_path, item.value, horizon_years=scenario.horizon_years,
            )
        self._validate_override_identifiers(
            scenario.indication_id, [i.parameter_path for i in overrides],
        )
        self._overrides.replace_for(scenario_id, [])
        self._write_overrides(scenario_id, overrides)
        self._session.flush()
        # The relationship was loaded before the swap, so the identity map
        # still holds the old collection; without expiring it the response
        # would echo back the overrides this call just deleted.
        self._session.expire(scenario, ["overrides"])
        return self.require(scenario_id)

    def clone(
        self,
        scenario_id: uuid.UUID,
        *,
        name: str | None = None,
        override_patch: Sequence[OverrideItem] = (),
    ) -> Scenario:
        """Copy the definition and every override; runs are never copied.

        The copy is taken from persisted state, so a scenario being edited in
        a client clones what was saved, not the draft (M1 section 6).
        """
        source = self.require(scenario_id)

        clone = Scenario(
            name=name or f"{source.name} (copy)",
            description=source.description,
            indication_id=source.indication_id,
            asset_name=source.asset_name,
            asset_class=source.asset_class,
            development_stage=source.development_stage,
            launch_year=source.launch_year,
            horizon_years=source.horizon_years,
            reporting_currency=source.reporting_currency,
            country_codes=list(source.country_codes),
            perspective=source.perspective,
            covered_population=source.covered_population,
            subgroup_codes=list(source.subgroup_codes or []),
            parent_scenario_id=source.scenario_id,
            is_baseline=False,               # a clone never inherits baseline
        )
        self._scenarios.add(clone)
        self._session.flush()

        # Patch entries replace the copied override on the same key rather
        # than sitting alongside it, which would violate the natural-key
        # uniqueness on (scenario, country, path).
        patched = {(p.country_code, p.parameter_path): p for p in override_patch}
        merged: list[OverrideItem] = [
            OverrideItem(
                country_code=o.country_code, parameter_path=o.parameter_path,
                value=o.value, note=o.note,
            )
            for o in source.overrides
            if (o.country_code, o.parameter_path) not in patched
        ]
        merged.extend(patched.values())

        for item in merged:
            validate_override(
                item.parameter_path, item.value, horizon_years=clone.horizon_years,
            )
        self._validate_override_identifiers(
            clone.indication_id, [i.parameter_path for i in merged],
        )
        self._write_overrides(clone.scenario_id, merged)
        self._session.flush()
        return self.require(clone.scenario_id)

    def set_baseline(self, scenario_id: uuid.UUID) -> Scenario:
        """At most one baseline per indication; the previous holder is
        cleared in the same transaction (M1 section 5.5)."""
        scenario = self.require(scenario_id)
        current = self._scenarios.get_baseline(scenario.indication_id)
        if current is not None and current.scenario_id != scenario_id:
            current.is_baseline = False
        scenario.is_baseline = True
        self._session.flush()
        return scenario

    def archive(self, scenario_id: uuid.UUID) -> None:
        """Soft delete. A scenario with runs must never be hard-deleted —
        `model_runs` references it, and a run whose parent vanished is no
        longer reproducible (M1 section 6)."""
        scenario = self.require(scenario_id)
        scenario.is_archived = True
        self._session.flush()

    # ----------------------------------------------------------------- runs

    def record_run(
        self,
        scenario_id: uuid.UUID,
        *,
        engine_version: str,
        run_type: str,
        input_snapshot: dict[str, object],
        fx_snapshot: dict[str, object],
        results: dict[str, object],
        duration_ms: int | None,
    ) -> ModelRun:
        """Append-only. Rows are never updated (M1 section 5.6)."""
        run = ModelRun(
            scenario_id=scenario_id,
            engine_version=engine_version,
            run_type=run_type,
            input_snapshot=input_snapshot,
            fx_snapshot=fx_snapshot,
            results=results,
            duration_ms=duration_ms,
        )
        self._runs.add(run)
        self._session.flush()
        return run

    def list_runs(self, scenario_id: uuid.UUID, *, limit: int = 20) -> Sequence[ModelRun]:
        self.require(scenario_id)
        return self._runs.list_for_scenario(scenario_id, limit=limit)

    def require_run(self, run_id: uuid.UUID) -> ModelRun:
        run = self._runs.get(run_id)
        if run is None:
            raise EntityNotFoundError(f"no run {run_id}", run_id=str(run_id))
        return run

    def require_comparable(self, scenario_ids: Sequence[uuid.UUID]) -> list[Scenario]:
        """2–4 scenarios that share an indication (M1 sections 5.7 and 6)."""
        if not (MIN_COMPARE <= len(scenario_ids) <= MAX_COMPARE):
            raise ValidationError(
                f"compare takes {MIN_COMPARE} to {MAX_COMPARE} scenarios, "
                f"got {len(scenario_ids)}",
                count=len(scenario_ids),
            )
        scenarios = [self.require(sid) for sid in scenario_ids]
        indications = {s.indication_id for s in scenarios}
        if len(indications) > 1:
            raise ConflictError(
                "every scenario in a comparison must share one indication; got "
                f"{sorted(indications)}",
                indication_ids=sorted(indications),
            )
        return scenarios

    # ----------------------------------------------------------------- internals

    def _write_overrides(
        self, scenario_id: uuid.UUID, items: Sequence[OverrideItem],
    ) -> None:
        for item in items:
            self._overrides.add(ScenarioOverride(
                scenario_id=scenario_id,
                country_code=item.country_code,
                parameter_path=item.parameter_path,
                value=item.value,
                note=item.note,
            ))

    def _validate_override_identifiers(
        self, indication_id: int, paths: Sequence[str],
    ) -> None:
        """Check the identifier inside a path against the seeded data.

        `validate_override` checks a path against the closed vocabulary and
        the value against its range, but it is a pure function with no
        session, so it cannot know whether `criteria.bmi_ge_35.factor` names a
        criterion that exists. The templates are regexes over
        `[A-Za-z0-9_]+`, so a misspelled code matched, stored, and was then
        skipped by the engine, which only ever iterates the seeded rows. The
        override looked accepted and did nothing.

        Resolved lazily and once per kind, so a scenario with no overrides of
        a given kind costs no query.
        """
        known: dict[str, set[str]] = {}

        def codes(kind: str) -> set[str]:
            if kind not in known:
                if kind == "criteria":
                    known[kind] = {
                        row.criterion_code
                        for row in self._reference.list_criteria(indication_id)
                    }
                elif kind == "subgroup":
                    known[kind] = {
                        row.subgroup_code
                        for row in OutcomesRepository(
                            self._session
                        ).list_subgroups(indication_id)
                    }
                else:  # therapy / substitution, both keyed by drug_id
                    known[kind] = {
                        str(row.drug_id)
                        for row in self._reference.list_drugs_with_regimens(
                            indication_id
                        )
                    }
            return known[kind]

        for path in paths:
            segments = path.split(".")
            head = segments[0]
            if head in {"criteria", "subgroup"} and len(segments) >= 2:
                kind, code = head, segments[1]
            elif head == "therapy" and len(segments) >= 2:
                kind, code = "therapy", segments[1]
            elif head == "substitution" and len(segments) == 2:
                # `substitution.naive` is a literal, not a drug id.
                if segments[1] == "naive":
                    continue
                kind, code = "therapy", segments[1]
            else:
                continue

            valid = codes(kind)
            if code not in valid:
                raise ValidationError(
                    f"{path!r} names {code!r}, which is not a "
                    f"{'criterion' if kind == 'criteria' else kind} in "
                    f"indication {indication_id}; available: {sorted(valid)}",
                    parameter_path=path,
                )

    def _validate_definition(
        self,
        indication_id: int,
        country_codes: Sequence[str],
        currency: str,
        subgroup_codes: Sequence[str] = (),
    ) -> None:
        if self._session.get(Indication, indication_id) is None:
            raise ValidationError(
                f"no indication {indication_id}", indication_id=indication_id,
            )

        # A segment code that names nothing was silently dropped, and the run
        # then modelled the whole diagnosed population while the request said
        # otherwise — a wrong denominator reported as a correct answer, which
        # is worse than a refusal. Checked here beside the market codes
        # because it fails for the same reason and deserves the same message.
        if subgroup_codes:
            known = {
                row.subgroup_code
                for row in OutcomesRepository(self._session).list_subgroups(
                    indication_id
                )
            }
            unknown_segments = [c for c in subgroup_codes if c not in known]
            if unknown_segments:
                raise ValidationError(
                    f"unknown subgroups for indication {indication_id}: "
                    f"{unknown_segments}; available: {sorted(known)}",
                    subgroup_codes=unknown_segments,
                )

        active = self._reference.list_active_country_codes()
        unknown = [c for c in country_codes if c not in active]
        if unknown:
            raise ValidationError(
                f"unknown or inactive markets: {unknown}", country_codes=unknown,
            )

        fx_rates, _ = self._reference.load_fx_snapshot()
        if currency not in fx_rates:
            raise ValidationError(
                f"no FX rate for reporting currency {currency!r}; available: "
                f"{sorted(fx_rates)}",
                reporting_currency=currency,
            )
