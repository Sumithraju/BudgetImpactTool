"""Scenario endpoints — M1 section 8.

Routes stay thin: declare the path, status and response model, call a
service, return. No business logic, no ORM queries, and no try/except —
domain exceptions are mapped centrally by the handlers in `main` (skill
section 8.4).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ..dal import get_session
from ..models.scenario import Scenario
from ..schemas.calculation import (
    CalculationResponse,
    CompareRequest,
    CompareResponse,
    CorridorEntryRead,
    EvidenceGapRead,
    EvidenceGapResponse,
    OwsaResponse,
    PsaResponse,
    RunDetail,
    RunRead,
    ScenarioDiffEntry,
    SolveRequest,
    SolveResponse,
    WarningRead,
)
from ..schemas.scenario import (
    OverrideItem,
    OverrideReplace,
    Page,
    ScenarioClone,
    ScenarioCreate,
    ScenarioRead,
    ScenarioUpdate,
)
from ..services.calculation_service import CalculationService
from ..services.evidence_gap_service import EvidenceGapService
from ..services.scenario_service import ScenarioService

router = APIRouter(prefix="/api/v1", tags=["scenarios"])

SessionDep = Annotated[Session, Depends(get_session)]


def _read(scenario: Scenario) -> ScenarioRead:
    return ScenarioRead(
        scenario_id=scenario.scenario_id,
        name=scenario.name,
        description=scenario.description,
        indication_id=scenario.indication_id,
        asset_name=scenario.asset_name,
        asset_class=scenario.asset_class,
        development_stage=scenario.development_stage,
        launch_year=scenario.launch_year,
        horizon_years=scenario.horizon_years,
        reporting_currency=scenario.reporting_currency,
        country_codes=list(scenario.country_codes),
        parent_scenario_id=scenario.parent_scenario_id,
        is_baseline=scenario.is_baseline,
        is_archived=scenario.is_archived,
        overrides=[
            OverrideItem(
                country_code=o.country_code, parameter_path=o.parameter_path,
                value=o.value, note=o.note,
            )
            for o in scenario.overrides
        ],
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


@router.post("/scenarios", response_model=ScenarioRead, status_code=status.HTTP_201_CREATED)
def create_scenario(
    payload: ScenarioCreate, session: SessionDep, response: Response,
) -> ScenarioRead:
    scenario = ScenarioService(session).create(payload)
    session.commit()
    response.headers["Location"] = f"/api/v1/scenarios/{scenario.scenario_id}"
    return _read(scenario)


@router.get("/scenarios", response_model=Page[ScenarioRead])
def list_scenarios(
    session: SessionDep,
    indication_id: int | None = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ScenarioRead]:
    scenarios, total = ScenarioService(session).list_scenarios(
        indication_id=indication_id, include_archived=include_archived,
        limit=limit, offset=offset,
    )
    return Page(
        items=[_read(s) for s in scenarios], total=total, limit=limit, offset=offset,
    )


@router.get("/scenarios/{scenario_id}", response_model=ScenarioRead)
def get_scenario(scenario_id: uuid.UUID, session: SessionDep) -> ScenarioRead:
    return _read(ScenarioService(session).require(scenario_id))


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioRead)
def update_scenario(
    scenario_id: uuid.UUID, payload: ScenarioUpdate, session: SessionDep,
) -> ScenarioRead:
    scenario = ScenarioService(session).update(scenario_id, payload)
    session.commit()
    return _read(scenario)


@router.put("/scenarios/{scenario_id}/overrides", response_model=ScenarioRead)
def replace_overrides(
    scenario_id: uuid.UUID, payload: OverrideReplace, session: SessionDep,
) -> ScenarioRead:
    scenario = ScenarioService(session).replace_overrides(scenario_id, payload.overrides)
    session.commit()
    return _read(scenario)


@router.post(
    "/scenarios/{scenario_id}/clone",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
def clone_scenario(
    scenario_id: uuid.UUID, payload: ScenarioClone, session: SessionDep,
) -> ScenarioRead:
    scenario = ScenarioService(session).clone(
        scenario_id, name=payload.name, override_patch=payload.override_patch,
    )
    session.commit()
    return _read(scenario)


@router.post("/scenarios/{scenario_id}/baseline", response_model=ScenarioRead)
def set_baseline(scenario_id: uuid.UUID, session: SessionDep) -> ScenarioRead:
    service = ScenarioService(session)
    service.set_baseline(scenario_id)
    session.commit()
    return _read(service.require(scenario_id))


@router.delete("/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_scenario(scenario_id: uuid.UUID, session: SessionDep) -> None:
    """Archive, never hard-delete: `model_runs` references this row, and a
    run whose parent vanished is no longer reproducible."""
    ScenarioService(session).archive(scenario_id)
    session.commit()


# --------------------------------------------------------------------------- calculation


@router.post("/scenarios/{scenario_id}/calculate", response_model=CalculationResponse)
def calculate(
    scenario_id: uuid.UUID,
    session: SessionDep,
    persist: bool = True,
    project_landscape: bool = False,
) -> CalculationResponse:
    """The forward run. Persists an append-only snapshot by default, so the
    result stays reproducible; `persist=false` is for interactive
    what-if editing, where writing a row per keystroke would be noise.

    `project_landscape=true` admits M14's pipeline entrants into the
    world-without. It is off by default and belongs beside the current-market
    result rather than in place of it: every entrant rests on three
    assumptions the evidence does not supply."""
    scenarios = ScenarioService(session)
    calculations = CalculationService(session)

    scenario = scenarios.require(scenario_id)
    response, engine_input, _ = calculations.calculate(
        scenario, project_landscape=project_landscape,
    )

    if persist:
        run = scenarios.record_run(
            scenario_id,
            engine_version=response.engine_version,
            run_type=CalculationService.run_type_forward(),
            input_snapshot=CalculationService.snapshot(engine_input, response)["input"],  # type: ignore[arg-type]
            fx_snapshot={
                "rates": dict(engine_input.fx_rates),
                "date": str(engine_input.fx_snapshot_date),
            },
            results=response.model_dump(mode="json"),
            duration_ms=response.duration_ms,
        )
        session.commit()
        response = response.model_copy(update={"run_id": run.run_id})

    return response


@router.get("/scenarios/{scenario_id}/owsa", response_model=OwsaResponse)
def owsa(scenario_id: uuid.UUID, session: SessionDep) -> OwsaResponse:
    scenario = ScenarioService(session).require(scenario_id)
    return CalculationService(session).owsa(scenario)


@router.get("/scenarios/{scenario_id}/psa", response_model=PsaResponse)
def psa(
    scenario_id: uuid.UUID,
    session: SessionDep,
    iterations: Annotated[int, Query(ge=100, le=50_000)] = 5_000,
    seed: int = 20_260_906,
) -> PsaResponse:
    scenario = ScenarioService(session).require(scenario_id)
    return CalculationService(session).psa(scenario, iterations=iterations, seed=seed)


@router.post("/scenarios/{scenario_id}/solve", response_model=SolveResponse)
def solve(
    scenario_id: uuid.UUID, payload: SolveRequest, session: SessionDep,
) -> SolveResponse:
    """Reverse mode: given an affordability ceiling, the highest price the
    asset could carry and still clear it in every market."""
    from biet_engine.solver import solve_price

    scenario = ScenarioService(session).require(scenario_id)
    engine_input, _ = CalculationService(session).build_input(scenario)
    corridor = solve_price(engine_input, payload.target_ratio)

    return SolveResponse(
        scenario_id=scenario_id,
        target_ratio=corridor.target_ratio,
        entries=[
            CorridorEntryRead(
                country_code=e.country_code,
                max_unit_price_usd=e.max_unit_price_usd,
                max_annual_acquisition_usd=e.max_annual_acquisition_usd,
                feasible=e.feasible, unbounded=e.unbounded,
                method=str(e.method), iterations=e.iterations,
                shortfall_usd=e.shortfall_usd,
            )
            for e in corridor.entries
        ],
        binding_market=corridor.binding_market,
        single_global_price_ceiling_usd=corridor.single_global_price_ceiling_usd,
        warnings=[
            WarningRead(
                code=w.code, message=w.message,
                country_code=w.country_code, parameter_path=w.parameter_path,
            )
            for w in corridor.warnings
        ],
    )


@router.get("/scenarios/{scenario_id}/runs", response_model=list[RunRead])
def list_runs(
    scenario_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RunRead]:
    runs = ScenarioService(session).list_runs(scenario_id, limit=limit)
    return [
        RunRead(
            run_id=r.run_id, scenario_id=r.scenario_id,
            engine_version=r.engine_version, run_type=r.run_type,
            duration_ms=r.duration_ms, created_at=r.created_at,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: uuid.UUID, session: SessionDep) -> RunDetail:
    """The full immutable snapshot — resolved inputs, FX set and results."""
    run = ScenarioService(session).require_run(run_id)
    return RunDetail(
        run_id=run.run_id, scenario_id=run.scenario_id,
        engine_version=run.engine_version, run_type=run.run_type,
        duration_ms=run.duration_ms, created_at=run.created_at,
        input_snapshot=run.input_snapshot, fx_snapshot=run.fx_snapshot,
        results=run.results,
    )


@router.post("/scenarios/compare", response_model=CompareResponse)
def compare(payload: CompareRequest, session: SessionDep) -> CompareResponse:
    """2-4 scenarios sharing an indication, calculated and diffed.

    The diff reports only paths where the scenarios actually disagree —
    listing every identical assumption would bury the handful that differ,
    which is the entire question a comparison is asked to answer.
    """
    scenarios_service = ScenarioService(session)
    calculations = CalculationService(session)

    scenarios = scenarios_service.require_comparable(payload.scenario_ids)
    results = [calculations.calculate(s)[0] for s in scenarios]

    names = [str(s.scenario_id) for s in scenarios]
    keys: set[tuple[str, str | None]] = set()
    for scenario in scenarios:
        keys.update((o.parameter_path, o.country_code) for o in scenario.overrides)

    diff: list[ScenarioDiffEntry] = []
    for path, country in sorted(keys, key=lambda k: (k[0], k[1] or "")):
        values: dict[str, float | str | bool | None] = {}
        levels: dict[str, str] = {}
        for name, scenario in zip(names, scenarios, strict=True):
            match = next(
                (
                    o for o in scenario.overrides
                    if o.parameter_path == path and o.country_code == country
                ),
                None,
            )
            values[name] = match.value if match else None
            levels[name] = "scenario_override" if match else "seeded default"
        if len(set(map(str, values.values()))) > 1:
            diff.append(ScenarioDiffEntry(
                parameter_path=path, country_code=country,
                values=values, resolution_levels=levels,
            ))

    return CompareResponse(
        scenario_ids=[s.scenario_id for s in scenarios],
        indication_id=scenarios[0].indication_id,
        reporting_currency=scenarios[0].reporting_currency,
        results=results, diff=diff,
    )


@router.get("/scenarios/{scenario_id}/evidence-gaps")
def evidence_gaps(scenario_id: uuid.UUID, session: SessionDep) -> EvidenceGapResponse:
    """Parameters ranked by influence times evidence weakness (M15).

    A tornado says which assumptions move the answer. This says which of
    those are worth doing something about — a high-swing parameter with a
    published country-specific source is settled, and a high-swing
    placeholder is the reason the answer cannot yet be trusted.
    """
    scenario = ScenarioService(session).require(scenario_id)
    report, currency = EvidenceGapService(session).rank(scenario)
    return EvidenceGapResponse(
        scenario_id=scenario_id,
        currency=currency,
        max_swing=report.max_swing.amount,
        gaps=[
            EvidenceGapRead(
                parameter_path=g.parameter_path,
                label=g.label,
                swing=g.swing.amount,
                influence=g.influence,
                confidence_tier=str(g.confidence_tier),
                weakness=g.weakness,
                priority_score=g.priority_score,
                priority=str(g.priority),
                source=g.source,
                has_provenance=g.has_provenance,
            )
            for g in report.gaps
        ],
    )
