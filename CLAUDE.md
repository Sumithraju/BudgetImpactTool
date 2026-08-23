# BIET — Budget Impact Estimation Tool

Early-stage budget impact estimation for Pricing & Market Access. Produces indication-specific,
multi-country, ISPOR-aligned budget impact estimates in minutes, under explicit uncertainty.

## Authority

| Document | Covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **The specification.** Scope, modules, formulas, schema, API, delivery plan. |
| [docs/modules/](docs/modules/README.md) | **Per-module specs (M0–M10).** Contracts, logic, edge cases, tests, acceptance criteria. Read your module's spec before building it. |
| [.claude/skills/biet-backend/SKILL.md](.claude/skills/biet-backend/SKILL.md) | How to write backend code |
| [.claude/skills/biet-frontend/SKILL.md](.claude/skills/biet-frontend/SKILL.md) | How to write frontend code |

Working under `backend/` → use the **biet-backend** skill. Under `frontend/` → **biet-frontend**.
Where a skill and the architecture document disagree, the architecture document wins.

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · PostgreSQL 16 + pgvector
React 18 · TypeScript 5 · Vite 5 · TanStack Query · Zustand · Tailwind · Recharts/Plotly

Backend is layered: `routes → controllers → services → repositories → dal`, with `biet_engine`
as a pure calculation package underneath. Frontend is a single feature-sliced Vite app —
**no Module Federation**; boundaries are enforced by ESLint.

## Non-negotiables

1. **The engine is pure.** `biet_engine` performs no I/O of any kind. Values are resolved before it is called.
2. **Budget impact is incremental** — world-with minus world-without. Never the gross cost of the new therapy.
3. **ORM only.** No raw SQL outside Alembic migrations and the one documented pgvector query.
4. **No secrets in source.** Credentials, proxies and connection strings come from the environment.
5. **Rates are fractions** (`0.0–1.0`). Only presentation multiplies by 100.
6. **Money carries a currency code.** FX is snapshotted into the run, never looked up live.
7. **Years are launch-relative.** Y1 is the launch year; calendar year is derived for display only.
8. **Provenance never drops.** Source, vintage and confidence tier travel with every value to the UI.
9. **Runs are immutable.** Every calculation persists its resolved inputs, engine version and FX set.
10. **No magic values.** Closed sets are enums; numbers are named constants.

## Layout

```
backend/src/biet_engine/   pure calculation package
backend/src/biet_api/      routes, controllers, services, repositories, dal, models, schemas
frontend/src/              app/, features/<slice>/, shared/
data/ingestion/            source fetchers, transforms, publish
data/seed/                 curated reference seeds
docs/                      architecture specification
BI_REPO/                   source datasets and guideline corpus
```

## Status

Specification baselined. Implementation begins at Phase 1 (data foundation) per §15.
