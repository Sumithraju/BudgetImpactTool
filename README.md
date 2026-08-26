# BIET — Budget Impact Estimation Tool

Indication-specific, multi-market, ISPOR-aligned budget impact estimates for
Pricing & Market Access — in minutes, under explicit uncertainty.

Give it a therapy, a disease, a set of markets and a payer perspective, and it
returns what the therapy costs a budget holder **relative to the care it
displaces**, what that spend buys in avoided clinical events, and what would
have to change for the answer to change.

Every figure it reports carries the source it came from, its vintage and its
confidence tier. Where a value is an assumption rather than an observation, the
result says so on the figure rather than in a footnote.

---

## Contents

- [What it does](#what-it-does)
- [Quick start with Docker](#quick-start-with-docker)
- [Install from source](#install-from-source)
- [Running it](#running-it)
- [Loading the reference data](#loading-the-reference-data)
- [Importing your own spreadsheet](#importing-your-own-spreadsheet)
- [Tests and checks](#tests-and-checks)
- [How the app is organised](#how-the-app-is-organised)
- [Troubleshooting](#troubleshooting)

---

## What it does

The interface is four steps, in dependency order — each one needs the one
before it:

| Step | | Why it comes here |
|---|---|---|
| **1 · Build** | who and where | Nothing else has a scope until the markets, disease and clinical subgroup are chosen. |
| **2 · Prices** | what it costs | A price is per market, so it needs step 1. Spreadsheet import lives here, because an import can change the market set. |
| **3 · Comparators** | what it displaces | Discovery searches by indication and target; promotion requires a price, so it needs both steps above. |
| **4 · Results** | what it means | The only step that reads rather than writes. |

The reason for the order is the arithmetic: budget impact is **incremental** —
world-with minus world-without — so the world-without has to be complete before
the subtraction means anything.

Results are nine tabs, in the order a formulary conversation runs: population
funnel, affordability, market access, budget impact, what it buys, subgroups,
payer view, uncertainty, report.

---

## Quick start with Docker

The fastest way to a running instance. You need Docker Desktop (or any Docker
Engine 24+ with Compose v2) and nothing else — no Python, no Node, no Postgres.

```bash
docker compose up --build
```

First run takes a few minutes: it builds both images, starts PostgreSQL with
the `pgvector` extension, applies the schema, and loads the reference data.
When it settles, open:

- **App** — http://localhost:5173
- **API docs** — http://localhost:8077/docs

The seeded reference data loads offline, but comparator discovery is live: it
calls Open Targets and Reactome while serving the request. If the container
cannot reach them, discovery reports that it could not reach the drug database
while the rest of the tool carries on working. Behind a corporate proxy, set
`HTTPS_PROXY` (and `NO_PROXY` for `db`) in the shell you run Compose from —
`docker-compose.yml` passes both through to the API and the migration step.

To stop:

```bash
docker compose down
```

To stop **and** delete the database volume, so the next start is completely
fresh:

```bash
docker compose down -v
```

---

## Install from source

Use this if you want to develop against it.

### Prerequisites

| | Version | Check with |
|---|---|---|
| Python | 3.12 or newer | `python3 --version` |
| Node.js | 20 or newer | `node --version` |
| PostgreSQL | 16, with `pgvector` | `psql --version` |

### 1 · Get the code

```bash
git clone https://github.com/Sumithraju/BudgetImpactTool.git
cd BudgetImpactTool
```

### 2 · Python environment

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

### 3 · Frontend dependencies

```bash
cd frontend && npm install && cd ..
```

### 4 · Database

On macOS with Homebrew:

```bash
brew install postgresql@16 pgvector && brew services start postgresql@16
```

On Debian or Ubuntu:

```bash
sudo apt install -y postgresql-16 postgresql-16-pgvector && sudo systemctl start postgresql
```

Then create the role, the database and the extension. This project's default
port is **5433** — adjust `-p` if yours runs on 5432:

```bash
psql -d postgres -p 5433 -c "CREATE ROLE biet LOGIN PASSWORD 'biet';"
```

```bash
createdb -O biet -p 5433 biet && psql -d biet -p 5433 -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

> **If `pgvector` has no package for your PostgreSQL version**, compile it
> against that version's `pg_config`:
>
> ```bash
> git clone --depth 1 --branch v0.8.1 https://github.com/pgvector/pgvector.git && cd pgvector && make && sudo make install
> ```

### 5 · Configuration

```bash
cp .env.example .env
```

The defaults match the database created above. Edit `.env` if your port,
password or host differ. **No secrets belong in source** — everything sensitive
is read from the environment.

### 6 · Schema and data

```bash
cd backend && ../.venv/bin/alembic upgrade head && cd ..
```

```bash
./.venv/bin/python -m data.ingestion.run --seed-only
```

That second command loads the curated reference data: markets, WHO indicators,
the obesity subgroups, drug prices and regimens, treatment effects and event
costs. Re-run it whenever you edit a file under `data/seed/`.

---

## Running it

One command starts both halves:

```bash
./run.sh
```

- **App** — http://localhost:5173
- **API docs** — http://localhost:8077/docs

`Ctrl-C` stops both. To run them separately:

```bash
./run.sh api
```

```bash
./run.sh ui
```

> The API starts with `--reload`. Keep it that way while developing: a server
> started without it keeps serving the code it launched with, and when the API
> contract has moved underneath it that looks exactly like a frontend bug.

---

## Loading the reference data

The ingestion CLI has four modes:

```bash
./.venv/bin/python -m data.ingestion.run --seed-only
```

Loads only the curated CSVs in `data/seed/`. Offline, fast, and the one you
want most of the time.

```bash
./.venv/bin/python -m data.ingestion.run
```

Fetches all six live sources (World Bank, WHO GHO, NADAC, openFDA,
ClinicalTrials.gov, Frankfurter) into `data/raw/` and transforms them. Takes a
few minutes; NADAC alone is a 124 MB download.

```bash
./.venv/bin/python -m data.ingestion.run --no-extract --publish
```

Re-runs the transforms against payloads already on disk and writes them to the
database — no network needed.

```bash
./.venv/bin/python -m data.ingestion.run --corpus
```

Embeds the guideline PDFs in `data/corpus/` for citation retrieval. Downloads a
~130 MB embedding model on first run, then works offline.

---

## Importing your own spreadsheet

The **Prices** step accepts Excel and CSV, and reads two shapes.

**The tool's own template** — download it from that screen. It arrives
pre-filled with your current price grid, so you correct what you disagree with
rather than typing every market from nothing. Every column carries the same
explanation you see on the inputs.

**Your own subgroup derivation** — a file with one row per country and columns
like `subgroup_1_diabesity_cases` / `subgroup_1_clinically_eligible`. It imports
unmodified; columns are matched by pattern, not by a fixed list.

Either way, nothing is saved by importing. You see exactly what the file was
read as, every rejected cell is reported with its sheet and row, and the values
land in the left-hand panel as **editable** inputs marked as coming from your
file. Anything the file did not cover stays on the model's seeded default.

---

## Tests and checks

```bash
./.venv/bin/python -m pytest backend/tests -q
```

```bash
./.venv/bin/mypy --strict backend/src
```

```bash
./.venv/bin/ruff check backend/src
```

```bash
cd frontend && npx tsc -b && npm run build
```

The ingestion suite runs fully offline — sockets are blocked by an autouse
fixture, so the offline guarantee is enforced rather than assumed:

```bash
./.venv/bin/python -m pytest data/ingestion/tests -q
```

---

## How the app is organised

```
backend/src/biet_engine/   pure calculation package — no I/O of any kind
backend/src/biet_api/      routes → services → repositories → dal
frontend/src/              app/, features/<slice>/, shared/
data/ingestion/            source fetchers, transforms, publish
data/seed/                 curated reference data, every row cited
docs/                      architecture spec, per-module specs, conventions
```

The engine is deliberately pure: it performs no I/O, and every value is
resolved before it is called. That is what makes a run reproducible — replaying
a stored snapshot through the recorded engine version returns the same answer.

Further reading:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the specification
- [`docs/modules/`](docs/modules/README.md) — per-module contracts and formulas
- [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) — the ten non-negotiables
- [`STATUS.md`](STATUS.md) — what is built, and the reasoning behind each decision

---

## Troubleshooting

**`could not connect to server` on startup.** PostgreSQL is not running, or is
on a different port from the one in `.env`. Check with `pg_isready -p 5433`.

**The app loads but every panel is empty.** The API is not running, or the
schema has no data. Check http://localhost:8077/health, then re-run
`--seed-only`.

**`extension "vector" is not available`.** `pgvector` is not installed for
*your* PostgreSQL version. See the note in step 4.

**Port 5173 or 8077 already in use.** Something else is on it — either stop
that, or set `PORT` for the frontend. The API port is in `run.sh`.

**A change to the API does nothing.** The API was started without `--reload`.
Restart it with `./run.sh api`.

**Comparator discovery says a data source is unavailable.** It calls Open
Targets and Reactome live. That is usually temporary — everything not relying on
those still works, and the tool says so rather than failing silently.
