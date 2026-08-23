# BIET — Current Status

**Last updated:** 2026-08-23 · **Phase:** 2 of 5 (Calculation Engine) — Phase 1 complete (§5),
**M6, M2, M3, M5, M4, M7 done** (§8) · **Deadline:** 2026-09-06

Read this first when resuming. It is the handoff document; everything else is reference.

**This machine (2026-08-23) has all of Phase 1 done:** git is initialized (main, clean),
PostgreSQL 16 + pgvector are installed on port **5433** (5432 is held by a separate EDB
PostgreSQL 18 install) with the full schema migrated to head, and the complete pipeline —
six live sources, all seed CSVs, the publish stage, and the guideline corpus — runs end to
end into that database. If you're reading this on a *different* machine, §1/§5.1 walk
through reproducing the database; the code and seed data travel through git as normal.

---

## 1. Resuming on another machine

### 1.1 Move the project first if it isn't under version control yet

On this machine `git init` has already been run — skip straight to §1.2. On a fresh machine,
do this first:

```bash
cd /path/to/BIET
git init
git add -A
git commit -m "BIET: specification baseline and Phase 1 data foundation"
```

`.gitignore` is already written and excludes `.venv/`, `.env`, and `data/raw/`.

**Two directories will not travel through git and must be handled separately:**

| Directory | Size | How to restore |
|---|---|---|
| `data/raw/` | 175 MB | Do not commit. Regenerate with `python -m data.ingestion.run` |
| `BI_REPO/` | 296 MB | Original Git-LFS repo. Clone it separately with `git lfs` installed, or leave it out — nothing in the new pipeline depends on it. |
| `.venv/` | 193 MB | Do not commit. Recreate from `requirements.txt` |

`BI_REPO/` was the original source repo. It is now **reference only** — the new pipeline in
`data/ingestion/` fetches everything itself. See §6 for the credential issue it carries.

### 1.2 Set up

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then edit; no proxy needed
```

Python 3.12+ (developed on 3.14.3).

### 1.3 Verify the setup works

```bash
./.venv/bin/python -m pytest data/ingestion/tests -q
```

Expect **33 passed**. The suite runs entirely offline — `conftest.py` blocks sockets — so this
works with no network and no database.

### 1.4 Run the pipeline

```bash
./.venv/bin/python -m data.ingestion.run                       # extract + transform only
./.venv/bin/python -m data.ingestion.run --no-extract --publish  # + write to Postgres
./.venv/bin/python -m data.ingestion.run --seed-only            # data/seed/*.csv only
./.venv/bin/python -m data.ingestion.run --corpus               # embed data/corpus/*.pdf
```

Expect `6/6 sources succeeded`. Takes a few minutes; NADAC is a 124 MB download. Add
`--no-extract` to re-run transforms against payloads already in `data/raw/`. `--publish`
needs a live database (§5.1) and needs `pip install -e backend` to have actually put
`biet_api` on the path — see the note in §5.2 about why that install can silently not work.
`--corpus` needs `fastembed`/`pypdf` (in `requirements.txt`) and downloads a ~130 MB model
from HuggingFace on first run.

---

## 2. What this project is

Early-stage budget impact estimation for Pricing & Market Access. Produces indication-specific,
multi-country, ISPOR-aligned budget impact estimates in minutes, under explicit uncertainty.

Built for the **Novo Nordisk Hackathon 2026, Problem #19**. Deliverables are a prototype, a deck
and a project report; judged on innovation, technical implementation, business impact, feasibility
and presentation.

**The positioning that keeps scope under control:** this is a decision-triage tool, not an
HTA-submission model. It answers "is this asset's budget impact a problem, where, and what do we
need to learn?" It does not replace the de novo budget impact model that comes later.

---

## 3. Where everything lives

```
BIET/
├── STATUS.md                    <- you are here
├── CLAUDE.md                    always-on project context; ten non-negotiables
├── requirements.txt             pinned dependencies
├── .env.example                 config template (no secrets)
│
├── docs/
│   ├── ARCHITECTURE.md          THE SPECIFICATION — 1,472 lines, 18 sections
│   ├── BIET_Architecture_Specification.docx   shareable Word version
│   └── modules/                 per-module specs M0–M10, 2,787 lines
│       ├── README.md            index, build order, shared contracts, golden case
│       └── M0..M10-*.md         one spec per module
│
├── .claude/skills/
│   ├── biet-backend/SKILL.md    how to write backend code (557 lines)
│   └── biet-frontend/SKILL.md   how to write frontend code (474 lines)
│
├── data/
│   ├── ingestion/                ALL PHASE 1 WORK IS HERE
│   │   ├── config.py             pydantic-settings; optional proxy
│   │   ├── constants.py          markets, indicators, thresholds — no literals elsewhere
│   │   ├── errors.py             exception hierarchy
│   │   ├── http.py               retry + backoff client
│   │   ├── base.py               Fetcher contract
│   │   ├── run.py                CLI entry point (--publish / --seed-only / --corpus)
│   │   ├── sources/              six fetchers
│   │   ├── transform/            EMPTY — unused; transform lives on each Fetcher instead
│   │   ├── publish/              writes seed CSVs, live sources and the corpus to Postgres
│   │   │   ├── seed.py           the seven table-owning seed CSVs
│   │   │   ├── live.py           worldbank / who_gho / frankfurter / nadac publishers
│   │   │   ├── corpus.py         PDF chunk + embed + publish (fastembed, local model)
│   │   │   ├── pipeline.py       orchestration, one transaction per source
│   │   │   └── upsert.py         generic upsert-by-natural-key
│   │   └── tests/                33 tests, offline
│   ├── seed/                     ten curated CSVs, all populated — see §5
│   ├── raw/                      gitignored; regenerate with the CLI
│   └── corpus/                   five ISPOR/NICE/WHO guideline PDFs, embedded
│
├── backend/
│   ├── alembic/                  schema migrations (two, both reversible)
│   ├── src/biet_api/              ORM models, config, DAL — routes/services not started
│   ├── src/biet_engine/           pure calculation package — M6,M2,M3,M5,M4,M7 done, M1/M8-M10 not started
│   └── tests/                     engine/{unit,property,golden}/, test_layering.py
├── frontend/                     EMPTY — Phase 3
└── BI_REPO/                      reference only; see §6
```

**Authority chain.** `ARCHITECTURE.md` says *what the system is*. `docs/modules/` says *what each
module does in detail*. The two skills say *how to write the code*. Where they conflict,
`ARCHITECTURE.md` wins.

---

## 4. Decisions locked

| Decision | Choice |
|---|---|
| Audience | Internal only. No payer-facing deployment, no compliance gating, no CRM. |
| Data strategy | Seeded defaults with full override; every value carries source + confidence tier. |
| Geography | Global multi-country rollup. Ten markets: USA, GBR, DEU, FRA, ITA, ESP, JPN, CHN, BRA, IND. |
| Model structure | Fixed canonical funnel with configurable levers. Not a general model builder. |
| Reverse mode | **In scope.** Given an affordability ceiling, solve for maximum price. This is M8. |
| Year convention | Launch-relative. Y1 is the launch year; calendar year derived for display only. |
| Therapy areas | Obesity and type 2 diabetes. |
| Frontend composition | Feature-sliced single Vite app. **No Module Federation** — boundaries enforced by ESLint. |
| ML / XGBoost / SHAP | **Out of scope.** Budget impact is deterministic arithmetic; uncertainty is handled by PSA, which is the ISPOR-recognised method. |
| Streamlit / Power BI / Supabase | Out. FastAPI + React per the coding guidelines. |

**The single most important technical rule:** budget impact is **incremental** — world-with minus
world-without. Never the gross cost of the new therapy. A model that reports gross cost overstates
impact by the full cost of displaced care.

---

## 5. Phase 1 status — complete

Every item M0's acceptance criteria (§11) asks for is done and verified against a live database
on this machine: `countries` (10, each with `adult_share` + `currency_code`), `country_economics`
(5 indicators × 10 countries), `epidemiology` (obesity 2024 with low/high; diabetes 2014 plus a
projected current-year row, flagged), `fx_rates` (7 currencies incl. USD identity), `drugs` /
`drug_regimens` / `drug_prices` (minimum comparator coverage, every price citing a source URL),
`funnel_defaults` / `eligibility_criteria` (both indications), `guideline_chunks` (embedded, ivfflat
index built and returning sensible nearest neighbours). Every published row across every table
carries `source` and `confidence_tier` — checked directly, zero nulls. `alembic check` reports no
drift; both migrations verified reversible; the 33-test offline suite still passes.

### Done

- **Secrets and config.** `pydantic-settings`, `.env.example`, `.gitignore`. Proxy fully optional;
  all endpoints (including HuggingFace for the embedding model) verified reachable without one.
- **Six source fetchers**, each with `extract → validate → transform`. Raw payloads written to disk
  unmodified, so transforms never touch the network.
- **WHO's four mandatory filters** (`apply_who_filters`) — drops income-group aggregates, region
  aggregates, single-sex series, non-adult age bands. Without these, aggregates load as markets.
- **Latest-non-null-year resolution**, per indicator per country independently.
- **Adult-share derivation with the 15–17 correction** — see §7.
- **NADAC** current-file resolution by walking Wednesdays backwards, plus dedupe by NDC keeping the
  latest effective date.
- **FX** with the USD identity row so M7 can pivot every conversion through USD without a special case.
- **CLI runner** with `--publish`, `--seed-only` and `--corpus` (`python -m data.ingestion.run`).
- **33 offline tests**, socket-blocked by an autouse `conftest.py` fixture — the offline guarantee
  is enforced, not assumed. Still pass; the publish stage isn't exercised by them (needs a live DB
  by design, so it's verified manually below instead).
- **Alembic schema**, two migrations, both verified reversible (upgrade → check → downgrade base →
  upgrade): the original sixteen tables, and a follow-up making `countries.adult_share` /
  `adult_share_source` nullable (§7). `docs/DATABASE.md` documents setup end to end.
- **PostgreSQL 16 + pgvector 0.8.1**, installed and running on this machine (§5.1).
- **The publish stage** (`data/ingestion/publish/`) — seed CSVs, live sources and the guideline
  corpus all write to Postgres, each source in its own transaction so one failure doesn't touch
  data another source already committed. `data/seed/*.csv` publish first so the live sources'
  foreign keys (drugs, indications, countries) resolve.
- **All ten seed CSVs**, cited (§5.3): `countries`, `indications`, `drugs`, `drug_regimens`,
  `drug_prices`, `funnel_defaults`, `eligibility_criteria`, `ndc_regimen_map`, `diabetes_cagr`.
  `age_bands.csv` is the one intentionally not written — see §5.4.
- **Diabetes forward projection** — implemented in `publish/live.py::publish_who_gho`, using
  `data/seed/diabetes_cagr.csv`. Verified: e.g. DEU 2014 5.0% → 2026 projection 7.145%
  (`is_projected=True`, tier C).
- **Guideline corpus** — the five ISPOR/NICE/WHO PDFs already downloaded into `BI_REPO/` (reference
  copy) were copied into `data/corpus/` and embedded with `fastembed` (`BAAI/bge-small-en-v1.5`,
  local, no API key or proxy — unlike `BI_REPO/ingests_pdfs_to_pgvector.py`, which hardcodes the
  IBAB proxy credential; see §6). 269 chunks across 5 documents. A sanity-check similarity query
  ("recommended time horizon for a BIA?") returned the WHO slide's "Time horizon: 5 years" section
  as the top hit — the embeddings are semantically meaningful, not just present.

Last verified full run: `6/6 sources succeeded` and `--seed-only`/`--corpus` both clean —
worldbank 50 rows, who_gho 30, nadac 28→3 published (25 NDCs correctly skipped, unmapped),
openfda 69, clinicaltrials 200, frankfurter 7, seed 45 rows across 7 tables, corpus 269 chunks.

### 5.1 Database — resolved on this machine

PostgreSQL 16 + pgvector are installed and running (Homebrew, port 5433 — 5432 is held by a
separate EDB PostgreSQL 18 install on this machine). The `biet` role/database exist, the `vector`
extension is created, and the schema migration is applied at head. See `docs/DATABASE.md` for the
full setup if this needs to be redone on another machine — the short version:

```bash
brew install postgresql@16 && brew services start postgresql@16
# pgvector's Homebrew bottle only targets PG 17/18 — for 16, compile against its pg_config
git clone --depth 1 --branch v0.8.1 https://github.com/pgvector/pgvector.git
cd pgvector && make PG_CONFIG=/opt/homebrew/opt/postgresql@16/bin/pg_config && make install PG_CONFIG=/opt/homebrew/opt/postgresql@16/bin/pg_config
psql -d postgres -p 5433 -c "CREATE ROLE biet LOGIN PASSWORD 'biet';"
createdb -O biet -p 5433 biet
psql -d biet -p 5433 -c "CREATE EXTENSION IF NOT EXISTS vector;"
cd backend && ../.venv/bin/alembic upgrade head
```

### 5.2 Gotcha: `pip install -e backend` may silently not work

This machine's Python (a python.org 3.13.5 build) **silently skips every `.pth` file** in
site-packages at startup — confirmed with `python -v -c pass`, which prints `Skipping hidden .pth
file` for `__editable__.biet_api-*.pth`, independent of any sandboxing. So `pip install -e backend`
appears to succeed (the `.pth` and `.dist-info` are written) but `import biet_api` still fails in a
fresh process. `data/ingestion/publish/__init__.py` works around this by inserting `backend/src`
into `sys.path` explicitly at import time, rather than depending on the editable install. If
`import biet_api` fails standalone but the pipeline runs fine, that's this — not a real problem —
but it's worth checking on a *different* machine whether the same interpreter quirk applies before
assuming the workaround is unnecessary there.

### 5.3 Seed data quality — what's solid, what's an estimate

Every seed row cites a source, per the non-negotiable, but the underlying confidence varies a lot
and every row's `confidence_tier` says so honestly:

- **Solid (tier A/B).** `countries`, `indications`, `drugs` are factual/structural. `drug_prices`
  for the seven US-market rows sourced directly from manufacturer pricing pages (`novocare.com`,
  `pricinginfo.lilly.com`) or NADAC (government data). `diabetes_cagr` — real World Bank
  `SH.STA.DIAB.ZS` (IDF Atlas-sourced) time series, 2011 vs 2024, same methodology both years, one
  API call per market away from being re-derived or extended.
- **Reasonable estimates (tier C), clearly flagged as such.** `drug_regimens.persistence_12m` —
  real published real-world studies exist and are cited, but persistence figures vary 2-3x across
  studies depending on definition and population, so these are informed midpoints, not precise
  observations. `funnel_defaults` and `eligibility_criteria` — several rows are genuine published
  statistics (obesity diagnosis documentation ~19%, diabetes undiagnosed ~43% globally / ~29% in
  high-income countries, T2D+CVD comorbidity 53% in a German cohort) but others (treated-given-
  diagnosed ratios, addressable-market fractions) are modelling assumptions with no direct citation
  — the source text says so explicitly in each case rather than presenting them as observed.
- **Only the US market is priced with branded (non-NADAC) data.** The other nine markets have no
  `drug_prices` row for the branded GLP-1s/comparators. This is intentional, not a gap: M5's own
  spec (§5.3) computes a PPP-derived price at *run time* for any market with no observed price —
  seeding placeholder prices for nine markets would just be pre-empting a Phase 2 engine function
  with worse-sourced numbers. `orlistat` and `metformin` are tier C — generic cash prices vary
  widely by pharmacy and were estimated from a reported range rather than one authoritative figure.
- **`price_local` unit design.** A real cross-check caught during this build: NADAC quotes
  insulin/liraglutide per mL, but M5's engine formula (`unit_price × units_per_admin ×
  admins_per_year`) needs `price_local` in the same unit as `drug_regimens.units_per_admin`, and
  `drug_regimens` has exactly one row per drug regardless of how many price bases exist for it. So
  NADAC's per-mL price is converted to per-IU (insulin) or per-mg (liraglutide) using the labelled
  concentration before it's stored — see the docstring on `publish/live.py::publish_nadac`. Verified
  by cross-checking `price_local × units_per_admin × admins_per_year` against the independently
  computed `annual_cost_usd` convenience field — they agree to the cent.

### 5.4 Deferred: `age_bands.csv`

M0's own §12 "open questions" already frames this as optional: overriding the tier-B 15-17-cohort
approximation with an observed UN World Population Prospects single-year figure would upgrade
`adult_share` to tier A and move results 3-6% per market, but the approximation is explicit,
sourced, and functions correctly without it. Not written this session; worth doing before the
numbers go in front of anyone who'd weight the difference between tier A and B.

---

## 6. Action items for you

1. **Rotate the IBAB account password.** `BI_REPO/datadownload.py`, `download_guidelines.py`,
   `ingests_pdfs_to_pgvector.py` and `app.py` contain it in plaintext (re-confirmed this session,
   reading `ingests_pdfs_to_pgvector.py` while designing the corpus embedding replacement). It is
   in git history, so deleting the line is not sufficient — the credential must be changed at the
   source. **Still open** — nothing in this session used or transmitted that credential; the
   replacement corpus script (`data/ingestion/publish/corpus.py`) needs no proxy at all on this
   machine.
2. ~~Install PostgreSQL 16 + pgvector~~ — done on this machine, see §5.1.
3. ~~Decide the diabetes CAGR source~~ — done: World Bank `SH.STA.DIAB.ZS` (IDF Atlas-sourced),
   same live API this pipeline already calls for other indicators. See §5.3.
4. **Optional: source observed 15-17 population shares** for `data/seed/age_bands.csv` — see §5.4.
   Not blocking anything.

---

## 7. Corrections made to the specifications

Recorded so nobody re-derives them or reverts them.

**Adult share was being derived wrongly.** `1 - pop_0014_pct/100` yields a **15+** share, but WHO
prevalence is **18+**. Uncorrected, this inflates the diseased population by 3.2 % (DEU) to 6.4 %
(IND). Now corrected by removing an approximated 15–17 cohort, confidence downgraded from tier A to
**B** (it is an approximation, not an observation), and overridable from `data/seed/age_bands.csv`.
Derived values 2026-08-23: USA 0.7948, GBR 0.7964, DEU 0.8334, FRA 0.8053, ITA 0.8601, ESP 0.8486,
JPN 0.8651, CHN 0.8151, BRA 0.7674, IND 0.7097.

**ARCHITECTURE.md §5.8 claimed the PPP price floor breaks solver linearity.** It does not: since
`max(a·p, b·p) = p · max(a, b)` for `p > 0`, the floor is a constant multiplier and the analytic
path stays valid. Left uncorrected, every India and China solve would have run bisection — up to
100× the work — for a case with a closed-form answer. Only tiered or volume-dependent discounting
genuinely forces the fallback.

**M7 must implement the full two-world subtraction, not the reduced form.** The reduced form assumes
`m_with = m_without − u·σ` exactly, which stops holding when M4's displacement floor binds and
redistributes. The reduced form becomes a property test instead.

**The golden case is a frozen synthetic fixture, not live data.** DEU `adult_share` derives to
0.8334 today against the fixture's 0.820. A golden fixture that moves when WHO refreshes an
indicator is not a golden fixture.

**`countries.adult_share` and `adult_share_source` had to become nullable.** The original schema
made them `NOT NULL`, but they're populated by a *different* pipeline stage (the World Bank live
source) than the rest of the row (curated `countries.csv` seed data) — two separate transactions by
design (M0 §5.7, "staged"). A country seeded before World Bank publishes is a real row with an
unresolved adult share, not a data-integrity violation. Migration `94bcd9ad76be` fixes this
(nullable columns, `CHECK` constraint amended to `adult_share IS NULL OR (... range ...)`),
verified reversible. If you're extending the schema and hit a similar `NOT NULL` failure on a
column populated by a different source than the row's other columns, this is probably why —
consider nullability before adding the constraint, not after the insert fails.

**`drug_prices.price_local` must be per clinical-dose-unit, never per the source's native unit.**
NADAC quotes insulin/liraglutide per mL; the seed data quotes everything else per mg. Since
`drug_regimens` has one row per drug regardless of how many `drug_prices` rows (bases) exist for
it, every basis for a drug must share the *same* unit convention or M5's `unit_price ×
units_per_admin` breaks the moment two differently-unit-quoted prices exist for one drug. See
§5.3's last bullet for the concrete fix; the general lesson is to check what unit `units_per_admin`
implies before writing a new price source's transform.

---

## 8. Next steps, in order

1. ~~`git init` and commit~~ — done (§1.1).
2. ~~Install PostgreSQL 16 + pgvector~~ — done (§5.1).
3. ~~Finish Phase 1~~ — done (§5): seed CSVs, publish stage, diabetes projection, guideline corpus
   all built and verified against a live database. Only the optional `age_bands.csv` (§5.4) and the
   IBAB password rotation (§6 item 1, not something a coding session can do) remain open.
4. ~~**M6 — Persistence**~~ — done. `biet_engine` now exists (`backend/src/biet_engine/`), with
   `persistence_fraction()`, the shared cross-module contracts (`models.py`), and the test scaffolding
   every later engine module reuses: `backend/tests/engine/{unit,property,golden}/` and
   `backend/tests/test_layering.py` (AST-based import-boundary check — biet_engine must never import
   fastapi/sqlalchemy/psycopg/httpx/requests/biet_api/pydantic_settings). 100% branch coverage,
   mypy --strict and ruff both clean. `requirements.txt` gained `hypothesis`, `mypy`, `ruff`.
5. ~~**M2 — Population Funnel**~~ — done. `biet_engine/funnel.py` implements `compute_funnel`
   per ARCHITECTURE.md §5.2. Along the way, `biet_engine/models.py` gained the full cross-module
   type system M2's own signature requires — `CountryInput` (M1), `Criterion` (M3), `Regimen`/
   `TherapyInput` (M5) — transcribed verbatim from those modules' own (already-written) contract
   sections, since `compute_funnel(country: CountryInput, ...)` can't be typed correctly without
   them. These are pure data containers with no logic; M3/M5's actual *computation* is still
   unbuilt. `biet_engine/constants.py` and `exceptions.py` also started here (`FunnelStage`,
   `CriterionType`, `PriceBasis` mirrored from `biet_api.constants.domain` — the engine can't
   import `biet_api`, so `test_constants_parity.py` guards the two from drifting apart;
   `FunnelInvariantError`, `UnresolvedParameterError`). One spec ambiguity resolved during
   testing: `criteria_factor > 1` raises `FunnelInvariantError` via the monotonicity check, not a
   second upfront `ValueError` — the module doc's own words ("monotonicity can only fail if a
   factor exceeds 1") say that's the intended path. 79 tests total, 100% branch coverage on
   `biet_engine`, mypy --strict and ruff clean.
6. ~~**M3 — Eligibility & Segmentation**~~ — done. `biet_engine/eligibility.py::combine_criteria`
   multiplies enabled criteria, propagates bounds only when every applied criterion has them,
   takes the weakest confidence tier, and guards correlated pairs — `strict=True` (default) raises
   `CorrelatedCriteriaError`, `strict=False` (for M9's sensitivity sweeps) returns a
   `CORRELATED_CRITERIA` warning instead. `CriteriaResult` gained a `warnings` field beyond the
   module doc's abbreviated contract — the only way a pure function can surface a non-fatal
   condition without raising or logging (biet-backend skill §8.6). A golden test wires M2+M3
   together (`combine_criteria`'s output straight into `compute_funnel`) and still reproduces the
   311,615 addressable figure. 96 tests total, 100% branch coverage across `biet_engine`,
   mypy --strict and ruff clean.
7. ~~**M5 — Cost & Pricing**~~ — done. `biet_engine/cost.py` has `compute_therapy_cost`
   (acquisition = unit_price × units_per_admin × admins_per_year × (1+wastage) × (1-discount),
   total = acquisition + admin + monitoring + AE − offset, never floored at zero) and
   `derive_ppp_price` (the cross-market PPP formula with its floor). `Money` gained `__add__`/
   `__sub__`/`__mul__` on the shared model — `__add__`/`__sub__` raise the new
   `CurrencyMismatchError` on a currency mismatch, so "no implicit conversion, ever" is enforced
   by the type itself rather than by callers remembering to check. `TherapyInput` gained a
   `price_provenance` field beyond M5's own abbreviated contract, for the same reason M3's
   `CriteriaResult` gained `warnings`: `TherapyCost.provenance` has to come from somewhere, and
   `unit_price: Money` carries no provenance of its own. One genuine spec-language puzzle resolved:
   "wastage-then-discount order... reverse order gives a different number" cannot literally be true
   for pure scalar multiplication (commutative) — what it's actually guarding against is collapsing
   the two adjustments into one additive term, `(1 + wastage - discount)`, instead of two
   multiplicative ones; the test documents this reading. `derive_ppp_price` stays a bare `float`
   per its literal contract — detecting whether the floor bound (for the `PPP_FLOOR_APPLIED`
   warning) is left to the caller, since wrapping a one-line formula in a result type to carry a
   warning would be a much bigger deviation from the spec than M3's one-field addition was.
   114 tests total, 100% branch coverage across `biet_engine`, mypy --strict and ruff clean.
8. ~~**M4 — Uptake & Market Mix**~~ — done. `biet_engine/uptake.py` has `project_uptake` (linear,
   logistic with defaults k=1.2/y_mid=N/2, and manual curves, each validated to [0,1] and checked
   for monotonicity unless `allow_erosion`) and `build_market_mix` (the world-without → world-with
   displacement, floor at zero, proportional redistribution of any deficit, with the ±1e-9 share
   accounting invariant asserted — not just tested — inside the function itself). `MarketMix`
   gained a `warnings` field beyond its abbreviated contract, same reasoning as M3/M5: a
   `SUBSTITUTION_FLOOR` warning has to come from somewhere when redistribution occurs, and a pure
   function can't log it. `displace()` uses `sigma.get(t, 0.0)` rather than the spec pseudocode's
   `sigma[t]` — a baseline therapy absent from the substitution vector is treated as drawing no
   new patients rather than crashing; the reverse case (a substitution entry naming a therapy not
   in the baseline set) still raises `UnknownTherapyError` as specified. 139 tests total, 100%
   branch coverage across `biet_engine`, mypy --strict and ruff clean.
9. ~~**M7 — Budget Impact Calculator**~~ — done. `biet_engine/impact.py::compute_budget_impact`
   is the definitional core: for every market and year it runs the full M2-M6 chain
   (`combine_criteria` → `compute_funnel` → `build_market_mix` → `compute_therapy_cost` +
   `persistence_fraction` per therapy) and executes the **full two-world subtraction**, not the
   reduced form — the module doc is explicit that the reduced form only holds when M4's
   displacement floor hasn't bound. The reduced form is used exactly as instructed: as a property
   test, agreeing with the full form to 1e-6 relative whenever no `SUBSTITUTION_FLOOR` warning
   fired. Cross-market aggregation converts every market's result to the reporting currency via
   the run's FX snapshot (pivoting through USD, never a live lookup), and picks the peak year with
   ties resolving to the earliest (a free consequence of Python's `max()` returning the first
   maximum encountered, not special-cased). The <200ms / 10-markets-x-5-years latency target is
   met by a benchmark test — with a plain Python loop, not NumPy, since 50 iterations of already-
   fast pure functions clears 200ms by a wide margin; vectorising now would be optimising against
   a guess rather than M9's actual PSA workload, which doesn't exist yet.

   Three real gaps found in the M1/M7 contracts as documented and fixed: `CountryInput` had
   nowhere to carry `m_without`/`sigma` (M7's own formula needs both directly) — added
   `baseline_shares`/`substitution`, matching the shape `build_market_mix` already expected.
   `EngineInput` was missing `fx_snapshot_date` even though `EngineResult` requires one and
   nothing else could supply it. `Totals` was referenced in M7's contract snippet but never
   defined anywhere — built from section 5.6's three formulas (`by_year`, `cumulative`,
   `peak_year`). `YearResult` also gained `net_cost_per_switch`, the same class of addition as
   M3/M4/M5's warnings fields: section 5.2 explicitly requires it be "expose[d]... in the
   response" and section 9 names a dedicated frontend component for it.

   One precision note worth remembering: the module doc's own golden-case worked example
   (net cost per switch EUR 2,452.92) is computed from the **4-decimal-place rounded** persistence
   fractions in the M6 reference table. This implementation calls `persistence_fraction()` itself
   and carries the full-precision result through, per section 5.7's "never round intermediate
   results" — correctly landing about EUR 3,500 away from the doc's rounded figure on a ~€38.2M
   budget impact (~0.01%). The test asserts the full-precision value, not the doc's rounded one.

   156 tests total (was 139), 100% branch coverage across `biet_engine`, mypy --strict and ruff
   clean.
10. **Next — M1 (Scenario Workspace), M8 (Affordability Solver), or M9 (Uncertainty &
    Sensitivity).** M1 is the resolution layer that actually builds `CountryInput`/`EngineInput`
    from DB rows + overrides — more backend-flavored (repositories, services) than the pure-engine
    modules so far, and the only thing standing between this engine and a real API. M8 depends on
    M5+M7, both done — it's the reverse solve (given an affordability ceiling, find the maximum
    price). M9 depends on M7+M8. Build order and the full dependency graph:
    [docs/modules/README.md](docs/modules/README.md).
10. Phase 3 — API and core UI. Phase 4 — solver, tornado, PSA. Phase 5 — narrative and export.

Build order and dependencies: [docs/modules/README.md](docs/modules/README.md).

---

## 9. Useful commands

```bash
# tests (offline, no database needed)
./.venv/bin/python -m pytest data/ingestion/tests -q

# full ingestion, transform only (no database needed)
./.venv/bin/python -m data.ingestion.run

# full ingestion + publish everything to Postgres (seed, live sources, in that order)
./.venv/bin/python -m data.ingestion.run --no-extract --publish

# seed CSVs only — countries/indications/drugs/regimens/prices/funnel/eligibility
./.venv/bin/python -m data.ingestion.run --seed-only

# guideline corpus only — chunk, embed (fastembed, local model) and publish the five PDFs
./.venv/bin/python -m data.ingestion.run --corpus

# re-transform without re-downloading
./.venv/bin/python -m data.ingestion.run --no-extract

# one source, verbose
./.venv/bin/python -m data.ingestion.run who_gho -v

# migrations (from backend/)
../.venv/bin/alembic upgrade head
../.venv/bin/alembic check              # model/database drift; must say "No new upgrade operations"

# regenerate the Word version of the architecture document
# (needs: npm install docx; script is in the session scratchpad — see note below)
node md2docx.js
```

**Note on the DOCX generator:** `md2docx.js` was written to a session scratchpad and is **not** in
the repo. If you need to regenerate the Word document after editing `ARCHITECTURE.md`, it must be
rewritten. Two gotchas it worked around: `docx-js` serialises paragraph border children in an order
that violates the OOXML schema when top/bottom are combined with left (use left+right only), and
two formula blocks use bracket-piece glyphs (`⌠⎮⌡`, `⎛⎝⎞⎠`) absent from most Windows monospace
fonts, so they are substituted with ASCII in the Word version only.
