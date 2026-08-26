---
name: biet-backend
description: "Engineering standards for BIET backend work — FastAPI, SQLAlchemy, Pydantic, and the pure calculation engine. Use whenever writing, reviewing, or refactoring anything under backend/ — routes, controllers, services, repositories, DAL, ORM models, schemas, the biet_engine package, ingestion scripts, migrations, or backend tests. Covers the layered architecture and its dependency rules, ORM-only data access, the repository/DAL pattern, constants and enums instead of literals, DRY and reuse rules, naming conventions, domain invariants for rates/currency/provenance, error handling, and the definition of done. Do NOT use for frontend work — see biet-frontend."
---

# BIET Backend Engineering Standards

Authority: [docs/ARCHITECTURE.md](../../../docs/ARCHITECTURE.md). This skill is *how* to build what that document specifies. Where the two disagree, the architecture document wins and this skill gets fixed.

Read the relevant architecture section before writing a module. ARCHITECTURE.md §5 for engine work, §7–8 for data, §9–10 for API.

---

## 1. Layered architecture — the rules

```
routes → controllers → services → repositories → DAL → database
                          ↓
                     biet_engine (pure)
```

Dependencies point **one direction only**. A layer may import the layer directly below it and the shared schema/constant modules. Nothing else.

| Layer | Does | Never does |
|---|---|---|
| `routes/` | Declares path, method, status codes, response model, OpenAPI metadata. One thin function per endpoint that calls a controller. | Business logic, DB access, calculation, try/except around domain errors |
| `controllers/` | Translates API schema ↔ service DTO. Maps domain exceptions to HTTP responses. | SQL, ORM queries, calculation, transaction management |
| `services/` | Business logic, value resolution, transaction boundaries, engine invocation, orchestration across repositories. | HTTP concerns (`Request`, `HTTPException`, status codes), raw SQL |
| `repositories/` | Query composition and persistence for **one aggregate**. Returns ORM models or engine/domain objects. | Business rules, cross-aggregate orchestration, HTTP concerns |
| `dal/` | Session lifecycle, engine creation, transaction primitives, base repository. | Domain-specific queries |
| `biet_engine/` | Pure calculation. | **Any** I/O — no DB, no network, no file access, no logging, no config reads |

### Enforcement

`tests/test_layering.py` asserts these boundaries by inspecting imports. Adding a violation fails CI. If you need to cross a boundary, the design is wrong — fix the design, not the test.

### The engine boundary is absolute

`biet_engine` imports nothing from `fastapi`, `sqlalchemy`, `httpx`, `requests`, `biet_api`, or any config module. It receives fully-resolved primitives and returns fully-computed results.

```python
# WRONG — engine reaching outward
def compute_funnel(country_code: str, session: Session) -> FunnelResult:
    country = session.query(Country).filter_by(code=country_code).one()   # NO
    default = settings.DEFAULT_DIAGNOSIS_RATE                             # NO

# RIGHT — everything resolved by the caller
def compute_funnel(inputs: FunnelInput) -> FunnelResult:
    ...
```

Resolution — walking the global default → country override → scenario override chain of ARCHITECTURE.md §7.3 — is `ResolutionService`'s job, and it happens **before** the engine is called.

---

## 2. Data access — ORM only

**Write queries with the SQLAlchemy 2.0 ORM. Do not write raw SQL strings.**

```python
# WRONG
rows = session.execute(text(f"SELECT * FROM epidemiology WHERE country_code = '{code}'"))

# RIGHT
stmt = (
    select(Epidemiology)
    .where(Epidemiology.country_code == code)
    .where(Epidemiology.indication_id == indication_id)
    .order_by(Epidemiology.year.desc())
)
return session.scalars(stmt).all()
```

Raw SQL is permitted in exactly two places, and nowhere else:

1. **Alembic migrations** — DDL and data backfills.
2. **pgvector similarity search**, where the `<=>` operator has no ORM expression. Wrap it in a single repository method, parameterise every value, and add a comment explaining why it is raw.

```python
# repositories/guideline_repository.py
# Raw SQL: pgvector's <=> distance operator has no SQLAlchemy ORM equivalent.
stmt = text("""
    SELECT chunk_id, chunk_text, 1 - (embedding <=> CAST(:qemb AS vector)) AS similarity
    FROM guideline_chunks
    ORDER BY embedding <=> CAST(:qemb AS vector)
    LIMIT :k
""")
return session.execute(stmt, {"qemb": embedding, "k": k}).all()
```

**Never** build SQL by string concatenation or f-string interpolation of user input. Ever.

### Repository pattern

One repository per aggregate. Repositories own queries; services own decisions.

```python
class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, pk: Any) -> ModelT | None: ...
    def add(self, entity: ModelT) -> ModelT: ...
    def list(self, *criteria: ColumnExpressionArgument[bool]) -> Sequence[ModelT]: ...


class EpidemiologyRepository(BaseRepository[Epidemiology]):
    model = Epidemiology

    def get_latest_for(self, country_code: str, indication_id: int) -> Epidemiology | None: ...
    def list_for_countries(self, codes: Sequence[str], indication_id: int) -> Sequence[Epidemiology]: ...
```

Method naming:

| Prefix | Returns | Missing row |
|---|---|---|
| `get_*` | Single entity or `None` | Returns `None` |
| `require_*` | Single entity | Raises `EntityNotFoundError` |
| `list_*` | `Sequence[Model]`, possibly empty | Returns `[]` |
| `add` / `update` / `delete` | The entity / `None` | — |

**Transactions belong to services**, not repositories. A repository never commits.

```python
class ScenarioService:
    def create(self, payload: ScenarioCreate) -> Scenario:
        with self._uow:                      # commits on exit, rolls back on exception
            scenario = self._scenarios.add(Scenario(**payload.model_dump()))
            self._overrides.replace_for(scenario.scenario_id, payload.overrides)
            return scenario
```

### N+1 is a defect

When loading related data, use `selectinload` / `joinedload`. A calculation touching ten markets must issue a bounded number of queries, not one per market.

---

## 3. Schemas — three families, never merged

Per ARCHITECTURE.md §9.2 these are deliberately separate. Do not "simplify" by sharing one model across layers.

| Family | Location | Purpose | Naming |
|---|---|---|---|
| API schemas | `schemas/` | HTTP request/response contract | `ScenarioCreate`, `ScenarioUpdate`, `ScenarioRead`, `CalculationRequest`, `CalculationResponse` |
| Engine models | `biet_engine/models.py` | Fully-resolved calculation input/output | `EngineInput`, `FunnelInput`, `CountryResult`, `EngineResult` |
| ORM models | `models/` | Persistence mapping | `Scenario`, `Country`, `Epidemiology` — singular PascalCase, table name plural snake_case |

Engine models have **no optional fields and no defaults**. If a value is optional, the service resolves it before constructing the engine input. An engine model that needs a default has leaked a decision into the wrong layer.

```python
# schemas/scenario.py — API: optional, client-friendly
class ScenarioCreate(BaseModel):
    horizon_years: int | None = Field(default=None, ge=1, le=5)

# biet_engine/models.py — engine: resolved, mandatory
class EngineInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    horizon_years: int = Field(ge=1, le=5)
```

Engine models are `frozen=True`. Calculation inputs are immutable.

---

## 4. Constants — no literals in logic

**No magic numbers. No magic strings. No hardcoded configuration.**

```
biet_api/constants/
├── __init__.py
├── domain.py      # closed sets → enums
├── defaults.py    # seeded defaults, analysis parameters
└── messages.py    # error codes and user-facing text

biet_engine/constants.py   # engine-only constants; engine never imports from biet_api
```

Closed sets are `StrEnum`, never bare strings:

```python
class AffordabilityBand(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"

class ConfidenceTier(StrEnum):
    A = "A"; B = "B"; C = "C"; D = "D"

class FunnelStage(StrEnum):
    TOTAL_POPULATION = "total_population"
    ADULT_POPULATION = "adult_population"
    DISEASED = "diseased"
    DIAGNOSED = "diagnosed"
    TREATED = "treated"
    LABEL_ELIGIBLE = "label_eligible"
    ADDRESSABLE = "addressable"

class UptakeCurve(StrEnum):
    LINEAR = "linear"; LOGISTIC = "logistic"; MANUAL = "manual"

class RunType(StrEnum):
    FORWARD = "forward"; REVERSE = "reverse"; OWSA = "owsa"; PSA = "psa"
```

Numeric parameters are named constants sourced from Appendix B of the architecture document:

```python
# constants/defaults.py
DEFAULT_HORIZON_YEARS: Final[int] = 3
DEFAULT_REPORTING_CURRENCY: Final[str] = "USD"
PSA_DEFAULT_ITERATIONS: Final[int] = 5_000
PSA_DEFAULT_SEED: Final[int] = 20_260_906
OWSA_DEFAULT_VARIATION: Final[float] = 0.20
SOLVER_RELATIVE_TOLERANCE: Final[float] = 1e-6
SOLVER_MAX_ITERATIONS: Final[int] = 100
CI_TO_SD_DIVISOR: Final[float] = 3.92          # normal approx. to a 95% interval
PPP_DEFAULT_ELASTICITY: Final[float] = 1.0
PPP_PRICE_FLOOR: Final[float] = 0.05

AFFORDABILITY_THRESHOLDS: Final[Mapping[AffordabilityBand, float]] = {
    AffordabilityBand.LOW: 0.001,
    AffordabilityBand.MODERATE: 0.005,
    AffordabilityBand.HIGH: 0.010,
}
```

Anything environment-specific — URLs, credentials, connection strings, proxies, API keys — lives in `config.py` via `pydantic-settings` and is read from the environment. **No secret, proxy string, or connection string appears in source, ever.** This is not negotiable; it is why ARCHITECTURE.md §13.4 exists.

---

## 5. Domain invariants

These prevent whole classes of silent wrongness in a financial model. Violating them produces plausible-looking numbers that are wrong, which is the worst failure mode this system has.

| Rule | Detail |
|---|---|
| **Rates are fractions** | Every rate, share, factor and probability is stored, passed and computed as `0.0–1.0`. Never `0–100`. Only the presentation layer multiplies by 100. Suffix percent-valued DB columns `_pct` and convert at the repository boundary. |
| **Money carries a currency** | No bare number represents money across a boundary. Use `Money(amount, currency_code)` or a field pair. Never add two amounts without asserting the currency matches. |
| **FX is snapshotted** | Conversion uses the rate set bound to the run, never a live lookup. Re-running a stored run must reproduce it exactly. |
| **Years are launch-relative** | `year=1` is the launch year everywhere internally. Calendar year is derived only for display: `launch_year + year - 1`. Never store calendar years in engine input. |
| **Provenance is never dropped** | A resolved value travels with `source`, `vintage_year`, `confidence_tier`. Any transform that discards provenance is a defect. |
| **Funnel is monotonic** | Each stage ≤ its predecessor. The engine asserts this and raises `FunnelInvariantError` rather than returning a wrong result. |
| **Floats in the engine, Decimal at the boundary** | `float64` inside `biet_engine` for vectorised numerics. Convert to `Decimal` when persisting monetary totals or serialising. Never accumulate currency in `float` outside the engine. |
| **Round once, at the edge** | Never round intermediate results. Round only when serialising, using the precision constants. |

---

## 6. DRY and reuse

Before writing a function, search for an existing one. Duplication of *logic* is a defect; duplication of *structure* usually is not.

- Shared calculation belongs in `biet_engine`, not copied into two services.
- Shared query shapes belong in a repository method, not repeated across services.
- Shared validation belongs in a Pydantic validator on the schema, not in every controller.
- Cross-cutting concerns — logging, timing, error mapping — belong in dependencies or middleware, not in each endpoint.

Extract on the **second** occurrence, not the first. A premature abstraction over one call site is worse than the duplication.

When a repository method differs from an existing one by a single filter, add a parameter — do not clone the method.

---

## 7. Naming

| Thing | Convention | Example |
|---|---|---|
| Module / package | `snake_case` | `calculation_service.py` |
| Class | `PascalCase` | `ScenarioService`, `EngineInput` |
| Function / variable | `snake_case` | `resolve_country_inputs` |
| Constant | `UPPER_SNAKE_CASE`, `Final` | `PSA_DEFAULT_ITERATIONS` |
| Enum member | `UPPER_SNAKE_CASE` | `AffordabilityBand.MODERATE` |
| Private | Leading underscore | `self._session` |
| Boolean | `is_` / `has_` / `should_` | `is_projected`, `has_override` |
| Engine function | Verb-first, pure | `compute_funnel`, `project_uptake`, `solve_price` |
| Test | `test_<unit>_<condition>_<expectation>` | `test_solve_price_infeasible_target_returns_infeasible` |

Domain vocabulary is fixed by Appendix A of the architecture document. Use `addressable`, not `eligible_final`. Use `persistence`, not `adherence` — they are different concepts. Use `budget_impact`, never `cost` or `spend`, for the incremental quantity.

---

## 8. Error and response handling

Handled **centrally, once**. No `try`/`except` in a route. No `HTTPException` outside the
exception handlers. No hand-built error dictionaries. If you are writing error-shaping code in a
route or controller, it belongs here instead.

### 8.1 Exception hierarchy

Two hierarchies, one per package. `biet_engine` exceptions know nothing about HTTP — that is what
keeps the engine pure.

```python
# biet_api/exceptions.py
class BietError(Exception):
    """Base for every domain error. Carries its own code and status."""
    code: ClassVar[str] = ErrorCode.INTERNAL
    status_code: ClassVar[int] = 500

    def __init__(self, message: str | None = None, **context: Any) -> None:
        self.message = message or self.__class__.__doc__ or self.code
        self.context = context
        super().__init__(self.message)


class EntityNotFoundError(BietError):
    """The requested resource does not exist."""
    code = ErrorCode.ENTITY_NOT_FOUND
    status_code = 404


class ValidationError(BietError):
    """The request is well-formed but semantically invalid."""
    code = ErrorCode.VALIDATION_FAILED
    status_code = 422


class ConflictError(BietError):
    """The operation conflicts with the current state."""
    code = ErrorCode.CONFLICT
    status_code = 409


class UpstreamUnavailableError(BietError):
    """A required external service is unavailable."""
    code = ErrorCode.UPSTREAM_UNAVAILABLE
    status_code = 503


# biet_engine/exceptions.py — no HTTP knowledge whatsoever
class EngineError(Exception):
    code: ClassVar[str] = "ENGINE_ERROR"

class FunnelInvariantError(EngineError):     code = "FUNNEL_NOT_MONOTONIC"
class UnresolvedParameterError(EngineError): code = "UNRESOLVED_PARAMETER"
class CurrencyMismatchError(EngineError):    code = "CURRENCY_MISMATCH"
class InfeasibleTargetError(EngineError):    code = "SOLVER_INFEASIBLE"
class DisplacementError(EngineError):        code = "DISPLACEMENT_NO_HEADROOM"
```

Adding a new error means adding one subclass. It does not mean touching any route.

### 8.2 Error codes are a shared registry

`constants/errors.py` is the single source of truth and is **exported to the frontend**, so both
sides speak the same vocabulary. Never invent a code inline.

```python
class ErrorCode(StrEnum):
    INTERNAL = "INTERNAL_ERROR"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CONFLICT = "CONFLICT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    # engine
    FUNNEL_NOT_MONOTONIC = "FUNNEL_NOT_MONOTONIC"
    UNRESOLVED_PARAMETER = "UNRESOLVED_PARAMETER"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    SOLVER_INFEASIBLE = "SOLVER_INFEASIBLE"
```

### 8.3 One error envelope

Every non-2xx response has this shape, without exception:

```python
class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None            # dotted path for field-level errors
    context: dict[str, Any] | None = None

class ErrorResponse(BaseModel):
    error: ErrorDetail                  # the primary error
    details: list[ErrorDetail] = []     # field-level errors, when applicable
    request_id: str
```

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Override value is outside the permitted range.",
    "field": "overrides[2].value",
    "context": {"parameter_path": "funnel.diagnosis_rate", "min": 0.0, "max": 1.0}
  },
  "details": [],
  "request_id": "01JP2K9X7A4M3QW8"
}
```

### 8.4 Centralised handlers

Registered once in `main.py`. These are the **only** places that construct an HTTP error.

```python
def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(BietError)
    async def _domain(request: Request, exc: BietError) -> JSONResponse:
        log.warning("domain_error", code=exc.code, path=request.url.path, **exc.context)
        return _error(request, exc.status_code, exc.code, exc.message, context=exc.context)

    @app.exception_handler(EngineError)
    async def _engine(request: Request, exc: EngineError) -> JSONResponse:
        # Engine errors are almost always bad input, not bugs.
        log.warning("engine_error", code=exc.code, path=request.url.path)
        return _error(request, 422, exc.code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def _pydantic(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            ErrorDetail(code=ErrorCode.VALIDATION_FAILED, message=e["msg"],
                        field=".".join(str(p) for p in e["loc"][1:]))
            for e in exc.errors()
        ]
        return _error(request, 422, ErrorCode.VALIDATION_FAILED,
                      "Request validation failed.", details=details)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled", path=request.url.path)
        # Never leak an internal message or stack trace to the client.
        return _error(request, 500, ErrorCode.INTERNAL, "An internal error occurred.")
```

`_error()` is the single constructor of `ErrorResponse`. It stamps `request_id` from the
request-ID middleware.

### 8.5 Success responses

**No success envelope.** Return the resource model directly — this keeps the OpenAPI schema clean
and the generated frontend types simple, and it matches the response shape already fixed in
ARCHITECTURE.md §10.5. Do not introduce a `{ "data": ... }` wrapper.

Lists use one generic page model:

```python
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
```

Status codes, applied consistently:

| Code | Use |
|---|---|
| 200 | Successful read, update, or calculation |
| 201 | Resource created — include a `Location` header |
| 204 | Successful delete/archive with no body |
| 400 | Malformed request (rare — most input errors are 422) |
| 404 | `EntityNotFoundError` |
| 409 | `ConflictError` — e.g. mixed indications in a comparison |
| 422 | Validation failure, domain or engine |
| 503 | `UpstreamUnavailableError` — LLM or embedding service down |

### 8.6 Warnings are not errors

A condition that does not stop a calculation — stale vintage, a projected value, a tier-D input, a
PPP-derived price, a bound substitution floor — is a **warning**, returned in the response body,
never raised and never merely logged.

```python
class Warning_(BaseModel):
    code: str
    message: str
    country_code: str | None = None
    parameter_path: str | None = None
```

Warnings accumulate through resolution and calculation and surface in `EngineResult.warnings`.
Dropping a warning is the same class of defect as dropping provenance: the number still looks
right, and the reader loses the reason to doubt it.

### 8.7 Request IDs and logging

Middleware assigns a `request_id` to every request, binds it to the structured logger, returns it
in the `X-Request-ID` response header, and includes it in every error body. A user reporting a
problem quotes that ID and it resolves to the exact log line.

Logging is structured (key–value), never f-string interpolation into a message. Log at `warning`
for expected domain errors, `exception` for unhandled ones, and never log request bodies that
could contain assumption data the user considers sensitive.

### 8.8 Rules

- Never `except Exception: pass`. Catch the narrowest type and either handle it meaningfully or let
  it propagate to the handlers.
- Never catch an exception only to re-raise it as `HTTPException`. Raise the domain error; the
  handler maps it.
- Never return an error as a 200 with an `error` field in the body.
- Never leak an internal exception message, SQL fragment, or stack trace to a client.
- Services and repositories raise domain exceptions and never import `fastapi`.

## 9. Typing and quality gates

- Full type annotations on every function signature. `mypy --strict` passes on `biet_engine`.
- No bare `Any` on a public signature. No `# type: ignore` without a comment explaining why.
- `ruff` clean, line length 100.
- Engine coverage ≥ 95%; `impact.py` and `solver.py` at 100%.

---

## 10. Testing

Four classes, per ARCHITECTURE.md §9.4. A change to the engine is not done until all four still pass.

```
tests/
├── engine/
│   ├── unit/         # one function, hand-computed expectation
│   ├── golden/       # complete worked scenarios, fixtures under golden/fixtures/
│   └── property/     # hypothesis invariants
├── api/              # endpoint contract, mocked services
└── test_layering.py  # import-boundary enforcement
```

Invariants that must hold (hypothesis):

- Budget impact is zero when uptake is zero at every year.
- Budget impact is monotonically non-decreasing in the new therapy's price.
- Persistence fraction lies in `(0, 1]` for all `p₁₂ ∈ (0, 1]`.
- Funnel stages are monotonically non-increasing.
- **Reconciliation:** the reverse solver's output price, fed through the forward calculation, reproduces the target affordability ratio within tolerance.

Golden fixtures are authoritative. Changing a golden result requires a version bump and an explicit note in the PR describing why the number moved.

---

## 11. Engine versioning

`biet_engine.__version__` is semantic. **Any change that alters a numerical result is at minimum a minor bump.** The version is written into every run snapshot, so a stale version makes historical runs irreproducible. Bump it in the same commit as the behaviour change.

---

## 12. Definition of done

- [ ] Layer boundaries respected; `test_layering.py` passes
- [ ] No raw SQL outside migrations and the documented pgvector method
- [ ] No magic numbers or strings; closed sets are enums
- [ ] No secrets, proxies, or connection strings in source
- [ ] Errors raised as domain exceptions; no `try`/`except` or `HTTPException` in routes or controllers
- [ ] New error codes added to the `ErrorCode` registry, not inlined
- [ ] Non-fatal conditions returned as warnings, not raised and not only logged
- [ ] Rates are fractions; money carries currency; provenance preserved
- [ ] Type annotations complete; `mypy` and `ruff` clean
- [ ] Unit tests added; golden fixtures updated if results moved
- [ ] `biet_engine.__version__` bumped if behaviour changed
- [ ] Alembic migration written and reversible if the schema changed
- [ ] Docstrings on public functions cite the architecture section they implement
