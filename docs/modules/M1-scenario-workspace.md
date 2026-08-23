# M1 — Scenario Workspace

Module specification v1.0 · Owner area: Backend + Frontend · Depends on: M0

---

## 1. Purpose

Manage the lifecycle of scenarios — the unit of work in BIET — and resolve their inputs into the
fully-materialised object the engine consumes. Owns creation, cloning, override management,
comparison, and the immutable run snapshot that makes every result reproducible.

## 2. Scope

**In scope.** Scenario CRUD; clone-with-override; baseline locking; the three-level value
resolution chain; override storage; run snapshot persistence; multi-scenario comparison.

**Out of scope.** Any calculation (M2–M9). Narrative or export (M10). Authentication and
multi-tenancy (out of system scope per ARCHITECTURE.md §1.4).

## 3. Dependencies

**Upstream.** M0 reference tables. **Downstream.** Every calculation module receives its input
from this module's `ResolutionService`.

## 4. Contracts

```python
# schemas/scenario.py — API layer
class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    indication_id: int
    asset_name: str = Field(min_length=1, max_length=200)
    asset_class: str | None = None
    development_stage: str | None = None
    launch_year: int = Field(ge=2026, le=2040)
    horizon_years: int = Field(default=3, ge=1, le=5)
    reporting_currency: str = Field(default="USD", min_length=3, max_length=3)
    country_codes: list[str] = Field(min_length=1)


class OverrideItem(BaseModel):
    country_code: str | None = None          # None → applies to all markets
    parameter_path: str                      # "funnel.diagnosis_rate"
    value: float | int | str | list[float]
    note: str | None = None


class ScenarioRead(ScenarioCreate):
    scenario_id: UUID
    parent_scenario_id: UUID | None
    is_baseline: bool
    overrides: list[OverrideItem]
    created_at: datetime
    updated_at: datetime


# biet_engine/models.py — engine layer: resolved, frozen, no defaults
class CountryInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    currency: str
    population_total: Valued
    adult_share: Valued
    population_growth: Valued
    prevalence: Valued
    health_exp_pc: Valued
    gdp_pc_ppp: Valued
    funnel: FunnelRates            # M2
    criteria: tuple[Criterion, ...]  # M3
    therapies: tuple[TherapyInput, ...]  # M5
    new_therapy: TherapyInput


class EngineInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: UUID
    indication_id: int
    launch_year: int
    horizon_years: int = Field(ge=1, le=5)
    reporting_currency: str
    fx_rates: Mapping[str, float]
    uptake: UptakeInput            # M4
    countries: tuple[CountryInput, ...]
```

`EngineInput` is frozen and has **no optional fields and no defaults**. Anything optional is
resolved here, before the engine is called.

## 5. Logic specification

### 5.1 Parameter paths

Overrides address values by dotted path. The path vocabulary is closed and defined in
`constants/parameter_paths.py`; an unknown path is rejected at validation.

| Path | Type | Range |
|---|---|---|
| `funnel.diagnosis_rate` | float | (0, 1] |
| `funnel.treatment_rate` | float | (0, 1] |
| `funnel.access_rate` | float | (0, 1] |
| `epidemiology.prevalence` | float | (0, 1) |
| `criteria.<criterion_code>.factor` | float | (0, 1] |
| `criteria.<criterion_code>.enabled` | bool | — |
| `uptake.curve` | str | `linear` \| `logistic` \| `manual` |
| `uptake.year_1` | float | [0, 1] |
| `uptake.terminal` | float | [0, 1] |
| `uptake.vector` | list[float] | each [0, 1], length = horizon |
| `therapy.<drug_id>.price_local` | float | > 0 |
| `therapy.<drug_id>.persistence_12m` | float | (0, 1] |
| `therapy.<drug_id>.market_share.<year>` | float | [0, 1] |
| `substitution.<drug_id>` | float | [0, 1] |
| `substitution.naive` | float | [0, 1] |

### 5.2 Resolution chain

Per ARCHITECTURE.md §7.3, each value resolves through three ordered levels, most specific wins:

```python
def resolve(self, path: str, country: str, ctx: ResolutionContext) -> Valued:
    for level, store in (
        (ResolutionLevel.SCENARIO_OVERRIDE, ctx.scenario_overrides),
        (ResolutionLevel.COUNTRY_OVERRIDE, ctx.country_defaults),
        (ResolutionLevel.GLOBAL_DEFAULT, ctx.global_defaults),
    ):
        hit = store.get((path, country)) or store.get((path, None))
        if hit is not None:
            return Valued(
                value=hit.value, low=hit.low, high=hit.high,
                provenance=Provenance(
                    source=hit.source, vintage_year=hit.vintage_year,
                    confidence_tier=hit.confidence_tier, resolution_level=level,
                    is_projected=hit.is_projected,
                ),
            )
    raise UnresolvedParameterError(path, country)
```

A scenario-level override with `country_code = None` applies to every market but is still
overridden by a scenario-level override naming that market explicitly.

**Provenance is mandatory.** A resolved value without provenance is a defect, not a convenience.
When an override supplies the value, provenance records `resolution_level = scenario_override`,
`confidence_tier = C`, and the user's note.

**Performance.** Resolution issues a bounded number of queries — batch-load all reference rows for
the scenario's markets and indication once, then resolve in memory. One query per parameter per
market is an N+1 defect.

### 5.3 Warning generation

Resolution emits warnings, which travel through the engine into the response:

| Code | Condition |
|---|---|
| `STALE_VINTAGE` | `launch_year − vintage_year > 5` |
| `PROJECTED_VALUE` | `is_projected` is true |
| `TIER_D_INPUT` | `confidence_tier == D` |
| `UNPRICED_MARKET` | price derived by PPP rather than observed (M5) |

### 5.4 Clone

Clone copies the scenario definition and **all** overrides, sets `parent_scenario_id`, clears
`is_baseline`, and appends `" (copy)"` to the name unless one is supplied. Optional
`override_patch` is applied after the copy. Runs are never copied.

### 5.5 Baseline

At most one scenario per indication carries `is_baseline = true`. Setting it clears the flag on
the previous holder within the same transaction.

### 5.6 Run snapshot

Every calculation persists to `model_runs` an append-only row containing the serialised
`EngineInput`, `biet_engine.__version__`, the FX rate set, results, and duration. Rows are
**never updated**. Replaying a run through the recorded engine version must reproduce the results
byte-identically.

### 5.7 Comparison

`POST /scenarios/compare` accepts 2–4 scenario IDs, requires a shared indication, executes or
retrieves the latest forward run for each, and returns aligned results plus a structured diff of
their resolved inputs (path, per-scenario value, resolution level).

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| `country_codes` must exist and be active | 422 with the offending codes |
| `indication_id` must exist | 422 |
| `reporting_currency` must have an FX row | 422 |
| Unknown `parameter_path` | 422, listing valid paths |
| Override value outside the path's range | 422 |
| `uptake.vector` length ≠ `horizon_years` | 422 |
| Substitution vector sums ≠ 1 (±1e-6) | 422 |
| Deleting a scenario with runs | Archive (soft delete); never hard-delete a run's parent |
| Cloning a scenario mid-edit | Clones the persisted state, not the client draft |
| Compare with mixed indications | 422 |

## 7. Data requirements

Reads all M0 reference tables. Writes `scenarios`, `scenario_overrides`, `model_runs`
(ARCHITECTURE.md §8.2).

Indexes: `model_runs (scenario_id, created_at DESC)`; unique
`scenario_overrides (scenario_id, country_code, parameter_path)`.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/scenarios` | 201, returns `ScenarioRead` |
| GET | `/api/v1/scenarios` | Filter by `indication_id`, paginated |
| GET | `/api/v1/scenarios/{id}` | Includes resolved inputs when `?resolved=true` |
| PATCH | `/api/v1/scenarios/{id}` | Partial update |
| POST | `/api/v1/scenarios/{id}/clone` | Optional `override_patch` |
| DELETE | `/api/v1/scenarios/{id}` | Soft archive |
| PUT | `/api/v1/scenarios/{id}/overrides` | Replaces the whole override set |
| GET | `/api/v1/scenarios/{id}/runs` | Run history |
| GET | `/api/v1/runs/{run_id}` | Full snapshot |
| POST | `/api/v1/scenarios/compare` | 2–4 IDs |

## 9. Frontend

Slice `features/scenario-builder/`.

- `ScenarioForm` — asset, indication, markets, launch year, horizon, reporting currency
- `MarketSelector` — multi-select over active countries with region grouping
- `OverridePanel` — per-parameter editing; each row shows current value, `<ProvenanceBadge>`,
  `<ResolutionIndicator>`, and a reset-to-default control
- `ScenarioList` — with clone, set-baseline, archive
- `ScenarioCompare` (slice `scenario-compare/`) — side-by-side with the input diff

Draft edits live in the Zustand `useScenarioStore`; persisted scenarios come from TanStack Query.
Never copy server data into the store.

## 10. Test specification

| Class | Test |
|---|---|
| Unit | scenario override beats country default beats global default |
| Unit | scenario override with `country_code=None` applies to all markets |
| Unit | explicit country override beats the all-markets scenario override |
| Unit | unresolved path raises `UnresolvedParameterError` |
| Unit | provenance records the correct `resolution_level` at each of the three levels |
| Unit | `STALE_VINTAGE` emitted when `launch_year − vintage_year = 6`, not when 5 |
| Unit | clone copies all overrides, sets parent, clears baseline, copies no runs |
| Unit | setting baseline clears the previous holder |
| Integration | resolution issues a bounded query count for 10 markets (assert ≤ N) |
| Integration | run snapshot replayed through the recorded version reproduces results exactly |
| API | override with out-of-range value returns 422 naming the path |
| API | compare with mixed indications returns 422 |

## 11. Acceptance criteria

- [ ] A scenario can be created, cloned, overridden and archived through the API
- [ ] `EngineInput` is fully resolved, frozen, and carries provenance on every value
- [ ] Resolution is batch-loaded; no N+1
- [ ] Run snapshots are append-only and replay identically
- [ ] Warnings surface for stale, projected and tier-D inputs
- [ ] Comparison works for 2–4 scenarios sharing an indication
- [ ] Frontend shows provenance and resolution level on every overridable value
- [ ] Layer boundaries respected; `test_layering.py` passes

## 12. Assumptions & open questions

**Assumptions.** Single organisation, no authentication. Scenario names need not be unique.
Archived scenarios remain readable.

**Open question.** Whether override history should be retained (an audit of who changed an
assumption and when) or only current state. Current schema stores current state only; adding
history is a separate table and does not change the resolution contract.
