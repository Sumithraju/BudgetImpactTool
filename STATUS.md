# BIET — Current Status

**Last updated:** 2026-08-25 · **Phase:** 12 of 18 — the budget impact model and the
comparator intelligence layer are complete; the outcomes layer is being built.
**Phases 1–11 complete**, bar one deliberate deferral (§8) · **Phase 12 under way** ·
**Phases 13–14 specified** after the first HEOR review (§9) · **Phases 15–18 specified**
after the second (§10) · **Deadline:** 2026-09-06

Read this first when resuming. It is the handoff document; everything else is reference.

**This machine has all eleven phases done.** `./run.sh` brings up the API on :8077 and the
interface on :5173; the database must already be running (§5.1). Start the API **with
`--reload`** — a server started without it serves the code it was launched with, which
looks exactly like a frontend bug when the contract has moved underneath it.

**Phase 1 detail:** git is initialized (main, clean),
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
│   ├── ARCHITECTURE.md          THE SPECIFICATION — 2,116 lines, 18 sections + 4A/4B/4C
│   ├── PROMPTS.md               one build prompt per phase, ready to hand to an engineer
│   ├── BIET_Architecture_Specification.docx   shareable Word version
│   └── modules/                 per-module specs M0–M22, 6,293 lines
│       ├── README.md            index, build order, shared contracts, golden case
│       └── M0..M22-*.md         one spec per module
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
│   ├── src/biet_api/              models, dal, repositories, services, schemas, routes, main
│   ├── src/biet_engine/           pure calculation package — every module built
│   └── tests/                     engine/{unit,property,golden}/, api/, test_layering.py
├── frontend/                      Vite + React, feature-sliced
│   └── src/
│       ├── app/                   App shell and the token stylesheet
│       ├── features/              scenario-builder/, results/
│       └── shared/                api client, formatters
├── run.sh                         starts API + interface together
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

### 5.5 Placeholder demo data — to be replaced with public sources

`scripts/demo_data.py` loads an invented dataset so every screen has something to show. It is a
stopgap, and **the intent is to replace it with the real thing from publicly available sources.**
Until then: `python scripts/demo_data.py purge` returns the database to seeded-and-cited data,
and `status` says what is which.

Everything it writes is tier D and carries `DEMO PLACEHOLDER` in its `source`, so it surfaces as
a placeholder through machinery that already exists — `TIER_D_INPUT` warnings, a critical M15
ranking, and a flagged row in the assumption register of every export.

**What is placeholder now, and what replaces it.** Grouped by how obtainable the real figure
actually is, because these are not the same problem:

| Placeholder | Rows | Public source that replaces it |
|---|---:|---|
| Prices for exenatide, lixisenatide, albiglutide | 3 | **CMS NADAC** — already the basis Saxenda uses, so the ingestion path exists. Manufacturer list-price disclosures for the branded ones |
| Regimens (dose, frequency) for all 7 | 7 | **openFDA / DailyMed labels** — already ingested by M0; dose and schedule are on the label |
| Adverse-event incidences | 32 | **ClinicalTrials.gov results API** — the method already worked this session for STEP 1, SURMOUNT-1 and SCALE. Verified 2026-08-25 that posted results exist in quantity for all three: exenatide **128** trials, lixisenatide **27**, albiglutide **24**. Picking the registrational one per drug is the work |
| Adverse-event unit costs, 9 markets | 36 | **NHS National Cost Collection** (GBR), **ATIH/GHS tariffs** (FRA), **EBM/DRG catalogues** (DEU), **MHLW fee schedule** (JPN). All published and downloadable |
| 12-month persistence for all 7 | 7 | Published retrospective claims analyses. No API — this one is a literature search, not a fetch |

**Four of the seven can never be replaced by an observation, and should stop being described as
placeholder.** Retatrutide, survodutide, danuglipron and efinopegdutide are unapproved: there is
no price to find, in any database, because none has been struck. Their prices are assumptions
now and will still be assumptions after every public source has been exhausted. The honest
treatment is the one M14 §5.5 already specifies — tier D, stated as an assumption, varied in
sensitivity analysis — not a note promising to look them up later.

The same is true of their adverse-event profiles in any indication they are not yet approved in,
and of every entrant plateau share.

---

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
5. **Replace the placeholder demo dataset with public sources** — see §5.5 for the table of what
   each row needs and where it comes from. Highest value per hour is the adverse-event
   incidences: the ClinicalTrials.gov results API already worked this session, and posted
   results exist for all three marketed therapies (checked — 128, 27 and 24 trials
   respectively). Lowest value is chasing prices for the four unapproved assets, which do not
   exist anywhere.
   **Run `python scripts/demo_data.py purge` before any number from this reaches a slide.**

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

## 9. HEOR review — 2026-08-25, and what it changed

Reviewed by the Global HEOR Lead. Three structural notes and two lists — an input taxonomy
and a dashboard. The lists were mapped against the build rather than accepted wholesale, and
**twelve of the twenty-five items were already delivered**; the coverage map lives in
ARCHITECTURE.md §4B so the mapping is checkable rather than asserted.

**What the review got right that the build had missed.** The gap was not scattered — it was
concentrated in one place. The model priced care and never valued its consequences. Every
missing output traced back to that: weight-loss responders, diabetes and cardiovascular
events avoided, hospital costs avoided. A payer asked to fund a therapy at $8,800 net per
switched patient asks what the $8,800 buys, and until now this tool could not answer.

**Three structural changes accepted.**

1. **One disease with subgroups, not two indications.** Obesity with type 2 diabetes is not
   obesity with established cardiovascular disease — different prevalence, different eligible
   fraction, different current care, and most consequentially different event rates. An
   averaged population describes neither. Becomes M18, and notably it is **M3 §12's deferred
   segmentation**, which STATUS previously recorded as too expensive to add. The review makes
   it necessary, and a cheaper design than the one M3 feared is available: a subgroup is a
   *scenario dimension*, so the engine runs unchanged once per segment and results aggregate.
   `biet_engine` stays pure and each segment keeps its own comparator mix.
2. **Perspective belongs to the payer, not the model.** An insurer covering four million
   lives, a self-insured employer covering forty thousand and a national health system read
   different denominators and count different costs. Becomes M17, which also carries PMPM
   (M8 computes PMPY today) and break-even price (M8 solves to an affordability target, not
   to zero).
3. **Flow reads inputs to outputs.** An interface ordering change — originally Phase 15,
   now Phase 17 with the rest of M21, after the second review (§10).

**Phase 12 — M16, Clinical Outcomes and Avoided Events. Engine built.** The pure module is
in `biet_engine/outcomes.py` with 20 unit tests and 5 property tests.

- Events avoided = exposed patients x baseline rate x relative reduction x effect retained.
- **Exposure is persistence-adjusted, not headline uptake.** An effect accrues only while a
  patient is on therapy; counting a discontinued patient as a responder overstates the
  clinical result and the economic one together.
- **Weight regain decays the effect** from year 2, and is full in year 1 by construction — a
  trial's reported effect *is* the year-one effect, so decaying it in the year it was
  measured would double-count regain the trial already observed.
- **The offset averages across the horizon**, not year 1. M5 carries one offset figure and
  the effect decays; taking year 1 would credit the therapy with its best year every year.
- **Nothing is inferred.** No effect is derived from a drug class, a mechanism or another
  therapy. A therapy with no supplied effect raises `NO_OUTCOME_EVIDENCE` — zero avoided
  events and no evidence about avoided events are different claims. A horizon extending past
  the trial's follow-up raises `EFFECT_BEYOND_FOLLOW_UP` naming the duration.
- Evidence located for seeding: **SELECT** (NCT03574597, 17,604 participants, composite MACE
  in overweight or obesity) for cardiovascular reduction, **STEP 1** for responder share.

**Still to build in Phase 12:** the `treatment_effects` and `event_costs` tables, the seed
from those trials, wiring the offset into M5, and the outcomes panel.

504 tests, mypy --strict and ruff clean.

---

## 10. HEOR review round two — 2026-08-25, and the plan it produced

A second review from the Global HEOR Lead, delivered the same day as the first and with a
working Streamlit prototype attached. Where the first review was a methodology brief, this one
is a usability brief: eight points, all of them about whether an HEOR manager can actually use
the thing. **Nothing in it contradicts the first review.** It is the same argument carried one
step further — a defensible number nobody can populate or read is not a deliverable.

Specified, not yet built. The output of this round is documentation: six module specifications,
a rewritten delivery plan and a build prompt per phase. No code changed.

### What the eight points asked for, and where each landed

| # | Point | Module | Phase |
|---|---|---|---|
| 1 | HEOR manager is the user; usability is the priority | M21 | 17 |
| 2 | Dynamic inputs — Excel import and editable dropdowns | M19 | 16 |
| 3 | Comparator set importable and editable | M19, M12 | 16 |
| 4 | Bounded database, frequently refreshed | M20 | 15 |
| 5 | Currency automated from country selection | M20 §5.6 | 15 |
| 6 | Population auto-filled from WHO; hover explanation, with and without intervention | M20 §5.7, M21 §5.2–5.3 | 15, 17 |
| 7 | The Streamlit prototype as the reference for flow | M21 §5.1 | 17 |
| 8 | Qwen or another Chinese-provider LLM on a free tier | M22 | 18 |

Point 6 splits because it is two asks in one sentence. The auto-fill half has been true since
Phase 1 — §7.3's resolution chain has resolved every funnel input from published data with
provenance from the beginning. What was missing was never the resolution; it was that a user
could not see it. That is why the work lands in M20 and M21 rather than in M2.

### What changed in the plan, and why

**The phase order moved.** Subgroups (M18) went from Phase 14 to Phase 13, ahead of payer
perspective. A subgroup changes the shape of a scenario, and the import contract, the payer
views and the entire interface all read that shape — building any of them first means building
them twice. Reference-data automation (M20) then precedes import (M19), because what a value is
worth has to be settled before a spreadsheet is allowed to overwrite it. The interface (M21)
comes after all three it renders. The gateway (M22) is last because it is the only one of the
seven the tool works completely without.

**Three new modules.** M20, M21 and M22 in a new §4C. M19 moved into that layer from §4B, where
it was specified in one paragraph and now has a full spec.

**Scope narrowed in §1.3.** One disease — obesity — with subgroups. Type 2 diabetes enters as
the `obesity_t2d` subgroup rather than as a second indication. §1.4 records the exclusion of a
disease library and why: one disease modelled with real subgroup structure is more useful to a
payer than several modelled as averages.

### Three things in the prototype deliberately not reproduced

The attached Streamlit app is a good specification of flow and a useful catalogue of what to
avoid. Its six-tab order — setup, population, comparators, new drug, uptake, results — is
essentially M21's nine stages, and its editable comparator grid is the surface the review named
twice. Three of its behaviours are not carried across:

1. **Currency is selected independently of market.** It is a separate dropdown offering ₹, $, €,
   £, R$ with no binding to the country chosen above it, so a German model can be denominated in
   rupees by accident. §6.2 and M20 §5.6 bind currency to market and convert only at
   presentation.
2. **Market shares that do not total 100% warn and are then used anyway.** The prototype computes
   a weighted comparator cost over shares summing to 94% and reports the result without
   qualification. M19 §5.3 rejects the file, and the interface shows a running total rather than
   discovering the problem at submission.
3. **Every input is a slider with no provenance.** Prevalence defaults to 2.5% for any disease in
   any country, and nothing records where that came from. Non-negotiable 8 is the whole
   difference between the prototype and this tool, and M20 §5.7 is where it becomes visible.

Worth saying plainly: the prototype does in 400 lines what it set out to do, and it made the
review's points more concrete than prose could. These are notes on what a production tool owes
that a prototype does not.

### On the LLM providers

Point 8 arrived with a comparison table of free tiers — ModelScope at roughly 2,000 calls a day,
Alibaba Model Studio at roughly a million tokens per model for ninety days, Hugging Face with a
small monthly credit. **Those figures are recorded in M22 as reported and are not verified by
this project.** Free tiers move, and a quota number written into a specification is stale the
moment a provider changes terms. The design does not depend on them: quota is counted before it
is spent, exhaustion is an ordinary failover, and no provider configured at all is a supported
state.

The review's own architecture sketch put the BIA calculation outside the LLM. That is already
non-negotiable 1 and §12.1, and it is the one point of agreement worth stating explicitly:
`NarrativeService` today hands the model text that is already correct and validates every number
in what comes back against the engine's own output. M22 generalises the provider and keeps that
validator exactly where it is — in `biet_engine`, pure, called by the gateway rather than the
other way round.

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
10. ~~**M8 — Affordability & Price Solver**~~ — done, in two modules.
    `biet_engine/affordability.py::compute_affordability` is the forward half: the ratio of BI to
    national health expenditure per year, the cumulative ratio as the **ratio of sums** (not the
    sum of ratios — they differ once population growth moves the denominator), and band
    classification, with a negative ratio classifying LOW as a saving.
    `biet_engine/solver.py::solve_price` is the reverse half: the analytic closed-form solve on
    the linear α/β decomposition, a bisection fallback that runs the real M7+M8 forward pass at
    trial prices, and the cross-market price corridor with its binding market.

    **Both reconciliation tests pass** — a solved price fed back through M7+M8 reproduces the
    target ratio to 1e-6 (analytic) and 1e-5 (bisection). The module doc calls these "the
    strongest single check in the system," and they do close the forward/reverse loop.

    The spec's own correction holds up in practice: the PPP floor does *not* break linearity
    (`max(a·p, b·p) = p·max(a, b)`), so a floor-bound market like India still takes the analytic
    path — asserted by a test. Only a `SUBSTITUTION_FLOOR` from M4 forces bisection, since that's
    what actually invalidates the reduced form the decomposition rests on.

    Three shared extractions came out of this rather than duplicating logic: `fx.py::convert`
    (M7 had it as a private helper; M8's two modules need the identical conversion),
    `funnel.py::project_population` (M8's affordability denominator needs M2's *projected*
    population, not the raw seeded value, without re-deriving the whole funnel), and
    `solver.py::_bisect` (generic bracketed bisection, split from the solver-specific
    bracket-widening/feasibility logic around it — which also made the non-convergence path
    directly testable). `CountryInput.health_exp_pc` became nullable for the same reason
    `adult_share` did: section 6 requires the unresolved state to reach the engine so it can
    raise rather than silently defaulting. `CorridorEntry` gained `shortfall_usd` and
    `PriceCorridor` gained `warnings` — the now-familiar pattern of a field the spec's prose
    requires but its abbreviated contract snippet omits.

    One documented simplification: the doc says a missing reference market is "permitted — ppp(ref)
    is still computable" but never says from *what*, so `solve_price` requires USA in the market
    set and raises `UnresolvedParameterError` otherwise, rather than inventing an undefined data
    source.

    190 tests total (was 156), **100% branch coverage across all of `biet_engine`**, mypy --strict
    and ruff clean. Both latency benchmarks assert green (<200 ms M7, <300 ms M8).
11. ~~**M9 — Uncertainty & Sensitivity**~~ — done, in three modules.
    `distributions.py` turns a published interval or a confidence-tier default into Beta / Gamma /
    Triangular parameters (Beta by method of moments, shrinking the SD with a `DISTRIBUTION_SHRUNK`
    warning rather than raising when it exceeds the variance ceiling).
    `sensitivity.py::run_owsa` is the tornado: `2N+1` forward evaluations, ranked by descending
    swing, with published bounds taking priority over tier defaults and rate ranges silently
    clipped to their domain. `psa.py::run_psa` is the Monte Carlo — **vectorised with NumPy**, not
    a loop, seeded through `default_rng` so a run reproduces exactly.

    **The M7 loop question, settled with a measurement.** Section 5.3 forbids a Python loop on the
    grounds that it "will miss the 5-second budget." Measured here: one `compute_budget_impact`
    call at 10 markets x 5 years is ~0.71 ms, so 5,000 looped calls would be ~3.5 s — *inside* the
    budget, so that stated premise is simply wrong. The section's other reason does hold: at the
    50,000-iteration ceiling a loop needs ~35 s. Vectorised, 5,000 x 10 markets runs in ~0.03 s.
    So M7's earlier "revisit when M9 exists" note resolves to: M7's scalar loop stays as it is,
    and PSA broadcasts separately.

    **The hazard that created, and its guard.** Vectorising means `psa.py` re-expresses M7's
    budget-impact arithmetic in array form — two implementations of one formula, which can drift
    silently. `test_psa_matches_compute_budget_impact_at_zero_variance` collapses every
    distribution to a point and asserts every draw equals `compute_budget_impact`'s scalar answer
    to 1e-9. That test is the thing keeping the two honest; do not delete it.

    An OWSA finding worth not misreading: with the default parameter set, every swing comes out
    *identical*. That is correct, not a bug — the funnel is a pure product, so an equal relative
    range on any one factor moves the product equally. A test asserts it with that reasoning
    written down, so nobody "fixes" it later.

    `ConfidenceTier` and `ResolutionLevel` moved from `models.py` to `constants.py` (re-exported,
    so existing imports still work): `constants` is documented as the home for closed sets, and
    `TIER_RELATIVE_STANDARD_ERROR` is keyed by tier, which would otherwise be a circular import.

    233 tests total (was 190), **100% branch coverage across all 16 engine modules**, mypy --strict
    and ruff clean. All four latency benchmarks green (<200 ms M7, <300 ms M8, <1 s OWSA, <5 s PSA).
12. **M10 — Evidence, Narrative & Export: the pure half is done; the I/O half is Phase 3.**
    M10 is the one module the doc itself scopes as "Backend + AI" rather than Engine, and most of
    it is I/O: pgvector retrieval, an LLM call, PDF/PPTX generation, five API endpoints. None of
    that can live in `biet_engine` (CLAUDE.md non-negotiable 1), and `biet_api` has no
    routes/services/repositories yet — so building it now would mean putting I/O in the wrong
    package. What *is* pure is in `biet_engine/narrative.py`:

    - **`validate_numbers`** — the post-generation half of §5.1's two-layer rule that *every*
      number in generated text comes from the engine, never the model. The doc calls its tests
      "the most important in this module"; they're written. It tolerates thousands separators and
      readable roundings ("38.2 million" for 38,218,333) because those are the same engine value
      presented differently — but rejects a plausible-looking computed number (the model doubling
      a population), which is the actual failure mode the rule exists to stop. Zero in context
      matches only zero, never acting as a wildcard.
    - **`MANDATORY_LIMITATIONS`** — §5.5's seven statements, each attributed to the module that
      owns the assumption, asserted present and distinct.
    - **`filter_by_similarity`** — §5.3's 0.35 floor; an empty result is a documented state
      (`NO_GROUNDING`), not an error.
    - **`build_assumption_register`** — §5.7's table, built from the run's own `EngineInput`
      snapshot rather than live reference data, so an export of an old run reflects what that run
      actually used.

    **Still to build, in Phase 3 when `biet_api` exists:** the pgvector retrieval repository (the
    one documented raw-SQL exception), prompt assembly + the LLM call, the ReportLab/python-pptx
    exporters, the copilot, and the five endpoints. The corpus they query is already embedded and
    indexed from Phase 1.

    258 tests total (was 233), 100% branch coverage across all 17 engine modules, mypy --strict
    and ruff clean.

    **The engine is now feature-complete for every module except M1.**
13. ~~**M1 — Scenario Workspace**~~ and ~~**Phase 3 — API + interface**~~ — done. BIET is now a
    working application, not a library.

    **Run it:**
    ```bash
    ./run.sh              # API on :8077, interface on :5173
    ```
    The database must already be up (§5.1). API docs at http://localhost:8077/docs.

    **What exists now:**
    - `backend/src/biet_api/` — schemas, services, repositories, routes, and one
      `main.py` that registers every exception handler. Ten endpoints: scenario
      create/list/read/update, override replace, clone, baseline, archive, calculate,
      OWSA, PSA, solve, run history, run snapshot, compare.
    - `frontend/` — feature-sliced Vite + React. Scenario builder on the left,
      results on the right: headline with credible interval, per-market table,
      population funnel with tier chips, tornado, PSA histogram.
    - **Verified end to end in a browser:** five markets, €2.71 bn cumulative,
      correct currency symbols per market, PPP-derived prices labelled as derived.

    **Two bugs the integration caught that unit tests structurally could not:**
    - `replace_overrides` returned the overrides it had just deleted. The delete and
      insert were correct; the relationship had been loaded before the swap and the
      identity map still held the stale collection. Fixed by expiring it after flush.
    - The OWSA tornado had both ends of the prevalence bar above the base case —
      impossible for a monotone parameter. `default_params` read bounds from
      `countries[0]` and wrote that *absolute* value into every market, forcing
      Japan's 5.9% obesity prevalence up to the USA's 38%. Now sweeps proportionally.
      Committed separately as `795f069`.

    347 tests, mypy --strict clean across 49 files, ruff and tsc clean.

14. ~~**Phase 4 — Analysis Capabilities**~~ — done. The engine and API already had all
    four; what was missing was reaching them from the interface.

    - **Affordability gauge** — logarithmic scale, and that is load-bearing: real ratios
      here run near 0.02% against a 1% critical threshold, so a linear axis would pin
      every market to the left edge. Band boundaries come from
      `/api/v1/reference/affordability-bands` rather than being duplicated in the
      frontend, because a threshold that drifted between the engine that classifies and
      the gauge that draws would mislabel a result without either side erroring.
    - **Price corridor** — M8's reverse mode. Running it across all five markets gave
      the result that makes the feature worth having: **India is the binding market at
      $746/unit**, down from $5,069 with only USA+DEU in scope. India's health
      expenditure is $85 per capita against the USA's $13,473, so a single global price
      is constrained by the poorest market in the set.
    - **Tornado and PSA** — already reachable from Phase 3.
    - **Scenario comparison** — 2-4 runs side by side; the diff lists only assumptions
      that actually differ. A parameter never touched shows as "seeded default" rather
      than its resolved value, because a seeded default and an override that happens to
      equal it are different claims.

    Verified in the browser: two runs at 23% and 46% treatment rate give EUR 2.71B and
    EUR 5.42B — exactly double, addressable doubling to match — and the diff isolates
    the one changed path. No console errors.

15. ~~**Phase 5 — Evidence, Export and Hardening**~~ — done. **A complete scenario now
    produces a distributable, fully cited deliverable**, which is the exit criterion for
    the whole project.

    - **Retrieval** — `repositories/guideline.py`, holding the one documented raw-SQL
      exception in the codebase (pgvector's `<=>` has no ORM expression). Queries the
      269 embedded chunks; the similarity floor is 0.35.
    - **Narrative** — two paths. The deterministic composer builds the account from the
      engine's own numbers and always works. The model path (Claude Opus 5) rewrites it
      more readably, then goes through `validate_numbers`; any figure absent from the
      engine output discards the whole draft. Without a credential the model path is
      skipped — an ordinary state, not a failure. `generated_by` tells the reader which
      path wrote the prose.
    - **Export** — PDF (6 pages) and PPTX (16:9), both with narrative, citations, the
      seven mandatory limitations, and the full 145-row assumption register.

    **The test caught a real inconsistency in my own code.** The deterministic composer
    was summing addressable populations across markets and stating the total — a number
    the engine never computed and the response does not contain. That is exactly what
    the validator rejects in a model draft, and the composer had quietly exempted
    itself. Fixed: it now quotes the largest market's figure, which is in the result.
    The rule applies to both paths or it is not a rule.

    354 tests, mypy --strict and ruff clean across 53 files, tsc clean.

16. **Phase 6 — competitive hardening.** Not in ARCHITECTURE.md §15; added after assessing
    what separates this from a commercial budget-impact tool. The engine was already
    rigorous — the gap was data quality and workflow fit, not calculation.

    - ~~**6.1 Excel export**~~ — **done.** Five sheets with **live formulas**, not a
      pasted grid: change a factor on the Funnel sheet and every stage below it
      recalculates; budget impact is `=cost_with − cost_without` in the cell, so the
      incremental rule is visible rather than asserted. Assumption register on its own
      sheet with tier colour-coding and an autofilter. HEOR runs on Excel; a model that
      cannot be re-checked in a spreadsheet does not fit the workflow it is built for.
    - ~~**6.2 Observed prices for DEU and GBR**~~ — **done.** Germany €301.91 per 28-day
      package (Novo Nordisk launch price, corroborated at ~$328/month by Peterson-KFF)
      and the UK £175.80/month NHS list. Both tier B, both stated in native currency,
      both with their caveats written into the source string — the German figure is a
      launch price rather than a verified Lauer-Taxe entry, and the UK figure is not
      verified against the Drug Tariff. Two markets moved off PPP derivation.

    **What 6.2 surfaced, and why it mattered more than the prices themselves.** With a
    real German price in place, Germany and the UK flipped to *negative* budget impact —
    a saving. That is not a bug and not quite a finding: Wegovy now carries an observed
    European price while every comparator in that market is still PPP-derived from
    inflated US list prices. Daily liraglutide derived from a US anchor looks far more
    expensive than weekly semaglutide at its real European price, so displacing it
    "saves" money. **The comparison is not like-for-like.** The system now raises
    `MIXED_PRICE_BASIS` naming any market whose therapies do not share one price basis.
    The result still stands — it is the best available given the data — but a reader who
    is not told would read it as clean. Three new integration tests cover it.

    - ~~**6.3 External validation**~~ — **done, and honestly scoped.** Not a reproduction
      of a published budget impact model: doing that faithfully needs another model's
      complete input set, and the published analyses located report their outputs
      without enough of their inputs to replicate. Claiming a match without matching
      assumptions would be an unearned credibility claim. What *is* verifiable is
      verified in `test_external_validation.py` — annual therapy cost reconciles to
      published list prices **exactly**, across two currencies and two molecules.

      It also caught something worth knowing: the engine's US annual cost is **8.3%
      above** the figure you get by quoting a monthly price twelve times, and the engine
      is right. A GLP-1 "monthly" package is 28 days, so a year is **13 packages, not
      12** — ×12 covers 336 days. Anyone reconciling this model against a spreadsheet
      built the other way will hit that discrepancy, so it is pinned with its
      explanation.
    - ~~**6.4 Observed German comparator prices**~~ — **done.** Tirzepatide €383/month at
      10 mg and liraglutide €291.92/month; German pharmacy prices are legally regulated
      and identical everywhere, which makes them genuine list prices. PPP derivation had
      been overpricing them by nearly 3× (€10,109 vs €4,979; €9,472 vs €3,552).
      **Germany moves from −€26.8m to +€45.1m**, net cost per switch from −729 to
      +1,227, and all three obesity therapies now cluster between €3,500 and €5,000 a
      year — the shape the market actually has.

      **The UK is deliberately left derived.** Its Wegovy figure is an NHS list price
      and the available comparator figures are private retail quotes; seeding those
      would swap one basis inconsistency for another. `MIXED_PRICE_BASIS` keeps firing
      for GBR, correctly. The warning now names the therapies on each side, because
      Germany (orlistat derived) and the UK (three comparators derived against one
      observed price) are materially different situations behind the same code.
    - ~~**6.6 Time benchmark**~~ — **done, measured not asserted.** A focused budget
      impact model takes **4–6 weeks** at an efficient consultancy and **12–18 weeks** at
      a larger firm (RxEconomics). Measured here, 5 markets over a 3-year horizon:
      forward calculation **0.04 s**, tornado **0.01 s**, PSA at 5,000 draws **0.05 s**,
      Excel workbook **0.48 s**, cited PDF **0.30 s** (warm — the embedding model is
      already loaded; a cold first call is slower). The complete deliverable is under a
      second.

    **Deliberately not done — 6.5 patient segmentation.** M3 §12 is explicit: adding it
    means `FunnelResult` returning a tuple of segments rather than a scalar, which
    changes the M4 and M7 contracts, and it says to "confirm before Phase 2 completes so
    the change is cheap if wanted." Phase 2 completed long ago, so this is now the
    expensive path — a contract-breaking change to a working, fully-tested system, for a
    feature that deepens something already defensible rather than fixing a gap. Twelve
    days from the deadline that is the wrong trade. Recorded here as a considered
    decision, not an oversight.

    362 tests, mypy --strict and ruff clean across 54 files, tsc clean.

18. **Phase 7 — Comparator Discovery (M11).** Done. The first of the five comparator
    intelligence modules specified in ARCHITECTURE.md §4A.

    Discovery answers the question that precedes every budget impact: *what would these
    patients receive if this asset did not exist?* Give it a gene symbol and an indication
    and it returns marketed and late-stage therapies acting on that target, classified into
    direct, therapeutic and pipeline, ranked, each with a rationale a reader can check.

    - **Retrieval is Open Targets alone, not Open Targets plus ChEMBL.** The spec planned
      both. Measured against the live endpoints, ChEMBL took **27 seconds** for a
      single-molecule lookup and rejected the batch filter outright, while Open Targets
      returns mechanism, action type and indications in the same sub-second call that
      returns the candidates. Two sources are not better than one when the second is slower
      than the timeout and supplies nothing the first does not.
    - **Open Targets' schema has moved.** The field is `drugAndClinicalCandidates`, not the
      `knownDrugs` that most documentation and most training data still describe;
      `Drug.isApproved` and `maximumClinicalTrialPhase` are gone and approval is read from
      `maxClinicalStage`. Verified against the live endpoint 2026-08-24, and the date is in
      the source. A renamed field fails loudly; a renamed *enum value* would not.
    - **Pathway expansion is the part that earns its keep.** Target-based retrieval on GLP1R
      cannot see a GIPR agonist — and for an obesity asset the GIPR and GCGR co-agonists are
      precisely the competitors that matter. Reactome's UniProt mapping gives the pathways;
      the most specific one (fewest participants — "Glucagon-type ligand receptors", 33, not
      "G alpha (s) signalling events", 158) is expanded into, its participants resolved in
      one batched call and queried in one more. Opt-in, because it costs ~6 s against ~1.4 s
      without it.
    - **A test caught a real defect.** `"agonist" in "antagonist"` is true, so substring
      matching classified every antagonist as an agonist — a drug doing the opposite of what
      was asked for, promoted to direct competitor. Fixed with word boundaries. The fixture
      that first "passed" was itself wrong: it kept an agonist mechanism string on an
      ANTAGONIST candidate, describing a molecule that cannot exist. A test built on an
      impossible fixture proves nothing, so the fixture now derives its mechanism text from
      the action type.
    - **Scoring is a weighted mean, not a fixed sum.** Market and line-of-therapy match are
      in the brief's score but no public source supplies either, so they participate only
      once M12 has curated them, and the score re-normalises over the factors actually in
      play. A candidate with no stated line of therapy is not scored as a *mismatch* — that
      would rank a well-documented poor match above a barely-documented good one.
    - **Measured, then reverted.** Probing three pathways is three independent round trips
      and the obvious move is to run them concurrently. Measured: median 1.42 s sequential
      against 1.72 s concurrent, inside the run-to-run noise. Reactome does not reward the
      machinery, so the machinery is gone and the measurement is in the comment explaining
      why.

    **Live behaviour**, GLP1R + obesity: 6 direct (semaglutide, tirzepatide, liraglutide,
    dulaglutide, exenatide, lixisenatide), 4 pipeline (retatrutide and survodutide at Phase
    III, efinopegdutide and avexitide), 9 excluded as indicated for another disease. Four of
    the six direct are already priced in this system; the rest are flagged `needs_pricing`
    and cannot enter a calculation until M12 exists to promote them.

    390 tests — 387 offline, plus 3 marked `network` and deselected by default so the
    standard run stays offline and deterministic. mypy --strict and ruff clean, tsc clean.

19. **Phase 8 — Comparator Registry and Asset Intake (M12).** Done. The hinge of the
    comparator layer: discovery returns molecules, M5 needs prices and regimens, and no
    public target database carries one. `comparator_assets` is where the two meet.

    - **Promotion is the act that makes a molecule usable.** One transaction writes the
      `drugs`, `drug_regimens` and `drug_prices` rows, or none of them. A comparator with a
      regimen and no price is not usable, and a half-promoted asset that *looks* promoted is
      worse than one that plainly is not.
    - **The guard, and why it is not a warning.** `require_promoted` raises
      `ComparatorNotPricedError` naming the asset. Silently dropping an unpromoted comparator
      would mean its cost is never subtracted from the world-without, and budget impact would
      be overstated by exactly the cost of the care the new therapy displaces — a wrong number
      that looks entirely reasonable. Tested; **called by M14 in Phase 10**, since a scenario
      does not yet name its comparator basket explicitly.
    - **Gaps are named per market.** `missing_for_promotion` returns `["price:DEU"]`, not a
      boolean, so the interface says "needs a German price" rather than "not ready". Only
      markets the asset is actually approved in are expected to have one — demanding a price
      everywhere would flag a US-only therapy as incomplete for nine markets it will never be
      sold in.
    - **No new engine contract, exactly as specified.** A promoted comparator carries an
      `indication_id`, and `list_drugs_with_regimens` already selects on that. Verified end
      to end through the browser: exenatide, discovered from Open Targets, registered and
      priced in the interface, appeared in the USA world-without on the next calculation with
      no engine change at all.

    **A latent defect surfaced, and it was not in this module.** Promotion failed on
    `drugs_pkey`. `drugs.csv` and `indications.csv` carry their own primary keys — the price,
    regimen and epidemiology files reference them, so a stable key is what lets those files be
    edited independently — but an insert with an explicit id **does not advance the
    sequence**. `drugs` was at `seq=1, max=11`; `indications` at `seq=0, max=2`. Every other
    seeded table lets the sequence assign and was fine.

    Promotion was simply the first code path that ever inserted a drug row, so it was the
    first thing to hit it. It would have failed identically for any future feature that
    writes reference data, with a duplicate-key error naming a primary key the caller never
    supplied — about as far from its cause as an error can get. Fixed in both directions: the
    publish stage now resyncs as it goes (`resync_sequence`), and migration `6418e7ab2864`
    repairs databases built before it did. Its `downgrade` is deliberately empty; re-breaking
    a database is worse than doing nothing.

    **Data hygiene.** The end-to-end check needed an exenatide price, and the figure used was
    invented for the test. It has been removed along with the asset, drug, regimen and price
    rows it created — a fabricated $425 unit price left in `drug_prices` would have silently
    changed every obesity scenario from then on.

    407 tests (3 network-marked), 20 of them new and against a real database, since promotion
    atomicity and re-promotion-in-place cannot be observed against a fake. mypy and ruff
    clean, tsc clean.

20. **Phase 9 — Safety and Adverse-Event Economics (M13).** Done. The module that lets this
    tool put a price on a safety difference without asserting one.

    - **Expected adverse-event cost** is incidence times unit management cost, summed. It
      populates M5's `ae_cost`, which until now was a hardcoded zero.
    - **Annualisation, which is not optional.** A trial reports over its exposure window,
      and none of the obesity trials ran for a year. Quoting a 68-week incidence as annual
      overstates it: semaglutide's 44.1% nausea is **35.9% a year**, tirzepatide's 31.9%
      over 72 weeks is **24.2%**. Under constant hazard, which overstates the back half of
      the year for events concentrated in titration — stated in the interface, not buried.
    - **The cost bridge** decomposes M7's net cost per switch across acquisition,
      administration, monitoring, adverse events and offsets. The terms sum to the total
      exactly, asserted as a property over random inputs rather than trusted, and the bridge
      reconciles to M7's budget impact in both directions. USA, Wegovy: acquisition
      **+$8,320**, adverse events **+$31**, net **$8,351** — against M7's 8350.852552, to
      within 2e-12.
    - **`AE_PROFILE_ASYMMETRIC` is the honest part.** Three of the five obesity therapies
      carry a profile; orlistat and no-pharmacotherapy do not, and are costed at zero. That
      biases the comparison *in their favour* — their event costs are missing, not absent —
      and the run says so rather than looking clean. The asymmetric case is the natural
      state of the data, not an edge case.
    - **Persistence is still not derived from tolerability.** Better tolerability plausibly
      raises persistence, and every link in that chain is defensible, and the chain as a
      whole is an inference. It stays a separately sourced M6 input.

    **Every incidence is real and checkable.** Taken from the trial registries, not from
    memory and not from a publication summary: STEP 1 (NCT03548935), SURMOUNT-1
    (NCT04184622), SCALE Obesity (NCT01272219), tier A, each row carrying its trial, its
    population and its exposure window. **This mattered.** Recall put semaglutide's nausea
    at 44.2% (registry: 44.1%) and tirzepatide 15 mg at 33.3%; a web search returned 21.9%
    for the same figure, quoting an n=311 subgroup. The registry says **31.9%** (201/630).
    Two of three sources were wrong, and the one that seeds the database is the registry.

    **Unit management costs are the weak half, and are labelled as such.** No trial reports
    what an event costs to manage. Each is an analyst construction with its arithmetic
    written into the source string — a fraction of a CPT 99213 primary-care visit (national
    average $95.19, CMS Physician Fee Schedule 2026) plus a medication cost. The price
    components are checkable; the consultation fractions are the assumption. All tier C, all
    raising `AE_COST_DERIVED`.

    **What the numbers actually say.** Adverse-event cost is $37–60 a year against
    acquisition costs of $13,000–17,500. On this evidence the safety difference between
    these therapies is economically negligible, and the tool says so rather than
    manufacturing a story. That is the module working, not the module failing.

    `biet_engine` **0.2.0** — results move for any therapy with a profile, so runs recorded
    under 0.1.0 are not comparable. 435 tests (3 network-marked), 28 new.

21. **Phase 10 — Launch-Year Competitive Landscape (M14).** Done. An asset launching in
    four years does not meet today's market, and a budget impact computed against the
    current mix silently assumes away every competitor approved in between.

    - Expected entry is derived from a trial's primary completion plus a stated 1.5-year
      regulatory lag, clamped at year 1 — an entrant already marketed at launch is an
      incumbent, not an entrant.
    - Entrants ramp linearly from their entry year; incumbents rescale **proportionally**,
      because no public source says which incumbent an entrant displaces. Nominating one
      would be a market-access judgement dressed as a computation.
    - Off by default, warns by name when on, and reported beside the current-market result
      rather than in place of it. Every entrant is three tier-D assumptions: that it is
      approved at all, when, and at what price.

    **Two real defects, both found by running it rather than by reading it.**

    First: **promoting a Phase III asset put it in the current market at a full incumbent
    share.** Promotion writes a `drugs` row, and everything in `drugs` for the indication is
    otherwise treated as marketed — so a registered pipeline drug silently asserted it was on
    sale today, which is exactly what M11 §5.3 separates the pipeline bucket to prevent.
    Unapproved therapies are now excluded from the world-without unless projection is on, and
    the exclusion is warned about (`PIPELINE_ENTRANT_EXCLUDED`) rather than silent.

    Second: **removing the entrant from the incumbent set left the shares summing to 5/6.**
    The engine refused the result, correctly — a mix that does not sum is not a market. The
    incumbents are now renormalised before entrants take share out of them.

    **Measured effect**, USA, one Phase III entrant at a 20% plateau from year 2: cumulative
    budget impact **$2.38bn against $2.06bn** — a 13% reduction, because the new asset now
    displaces a competitor that did not exist in the current-market baseline.

    **`require_promoted` is now live.** M12's guard had no reachable caller; M14 is it. An
    entrant with no price is skipped **by name**, as is one with no stated plateau share —
    two different situations, two different messages, neither of them silent.

    **A warning defect fixed in passing.** `AE_COST_DERIVED` was firing once per market with
    an identical message — five identical rows a reader stops reading. It now names every
    affected market once, and a market with *no* seeded adverse-event costs raises the
    separate `AE_COST_MISSING` instead: priced on a weak basis and not priced at all are
    different states, and merging them overstated what was known.

    459 tests (3 network-marked), 24 new.

22. **Phase 11 — Evidence-Gap Intelligence (M15).** Done, and the cheapest of the five to
    build because everything it needs already existed: M9 computes how much each input moves
    the answer, and every resolved value already carries a confidence tier. Neither alone
    answers the question an analyst actually has after reading a tornado, which is not "what
    is uncertain" but "what should I go and find out".

    ```
    influence = swing / max(swing)
    priority  = influence x weakness(tier)       A 0.05 · B 0.25 · C 0.60 · D 1.00
    ```

    **On the seeded USA scenario it reorders the tornado, which is the entire point:**

    | Parameter | Swing | Tier | Tornado rank | Evidence rank |
    |---|---:|:--:|:--:|:--:|
    | Treatment rate | €1.5bn | C | 1 | **1 — critical** |
    | Adult share | €1.28bn | B | 2 | **3 — medium** |
    | Access rate | €987m | C | 3 | **2 — high** |
    | Disease prevalence | €311m | A | 4 | **5 — sufficient** |

    Adult share has the second-largest swing in the model and is World Bank data. The
    tornado nominates it second; the evidence ranking correctly demotes it, because
    re-deriving a World Bank population series is not what will improve this answer.
    Prevalence moves €311m and is tier-A WHO data — settled. Treatment rate is derived
    rather than observed, and is where a week of research would actually pay.

    Two deliberate design points: **tier A is weighted 0.05, not zero**, so a published
    figure that dominates the tornado can still surface; and **a zero-swing parameter scores
    zero however weak its source**, because time spent pinning down a value that cannot move
    the result is time not spent on the one that can. A parameter with no provenance at all
    is treated as tier D *and flagged* — an admitted placeholder and an unattributed value
    score the same and are not the same problem.

    **In the deliverable, not only on screen.** The ranking is a page in the PDF and a
    slide in the deck, placed *before* the assumption register: the register says what every
    value rests on, this says which of those are worth doing something about, and a reader
    who stops early should have seen the shorter, more actionable list. If the ranking
    cannot be computed the export still builds without it — the ranking is an addition to
    the report, not the report.

    478 tests (3 network-marked), 19 new. Every acceptance criterion in M11–M15 is met.

---

**The comparator intelligence layer is complete.** The brief's "minimum demo story" runs
end to end, measured at **1.4 seconds** including the live Open Targets call:

```
GLP1R + obesity  →  6 direct, 4 pipeline, 7 excluded          (discovery, live API)
                 →  register a Phase II competitor, price it  (registry, 2 gaps named)
                 →  it enters the world-without               (no engine change)
                 →  current market  $2.38bn                   (world-with vs world-without)
                    market at launch $1.95bn                  (entrant admitted from year 2)
                 →  net cost per switch $8,351 =
                    acquisition +8,320, adverse events +31    (the bridge)
                 →  research priorities: treatment rate (critical),
                    access rate (high), adult share (medium)  (evidence gaps)
```

Every value on that path carries its source, its vintage and its confidence tier — and where
a value is an assumption rather than an observation, it says so in the output rather than in
a footnote.

**Data hygiene across all five phases.** Every figure invented to exercise a code path — the
exenatide price in Phase 8, the entrant prices in Phases 10 and 11 — has been removed. The
database holds 11 drugs, 16 prices and 12 adverse-event incidences, all seeded and all
cited. A fabricated price left in `drug_prices` would silently change every obesity scenario
from then on, which is precisely the failure this system is built to avoid.

17. **What remains outside the code.**
    - **The deck and the project report.** Hackathon deliverables in their own right,
      and mostly writing. The PPTX export is a starting point for the deck; the two
      published artifacts and this document cover much of the report's substance.
    - **`ANTHROPIC_API_KEY`** — set it and the narrative upgrades from deterministic
      prose to a validated model draft. Everything works without it.
    - **IBAB password rotation** (§6) and the optional **`age_bands.csv`** (§5.4).

    **Honest read:** every phase in the specification is complete and verified. The
    system ingests real data, computes a defensible incremental number, exposes it
    through an API and an interface, and exports a cited document. What is left is
    presentation, not construction.

18. **Phases 12–18 — the two HEOR review rounds.** Specified in full; Phase 12's engine
    module and the first slice of Phase 16 are the only parts built. The order below is dependency-driven and is explained in
    §10; a build prompt per phase is in [docs/PROMPTS.md](docs/PROMPTS.md).

    | Phase | Module | Delivers | State |
    |---|---|---|---|
    | 12 | M16 | Events avoided and the cost they carried | Engine built; tables, seed, M5 wiring and panel remain |
    | 13 | M18 | One disease with subgroups | Specified |
    | 14 | M17 | Perspective, PMPM, break-even, uptake bands | Specified |
    | 15 | M20 | Fresh bounded data, market-bound currency, auto-filled inputs | Specified |
    | 16 | M19 | Workbook import and editable inputs | Specified |
    | 17 | M21 | The guided interface | Specified |
    | 18 | M22 | Provider-agnostic LLM gateway | Specified |

    **Start with Phase 12's remainder, then Phase 13.** Finishing M16 is a day's work against
    a module that already passes its own tests, and M18 is the hinge — every phase after it
    reads the scenario shape it defines, so anything built ahead of it is built twice.

    **Built out of order, on 2026-08-25, after the tool was seen running.** Tabs, a
    new-intervention input and comparator import — the parts of Phases 16 and 17 an
    analyst hits first. The interface was one scrolling column with no way to enter the
    new therapy's own costs and no way to load a comparator set that already existed.

    - `Tabs` in `shared/`, WAI-ARIA keyboard pattern, replacing the scroll with six
      panels: Current care, Import, New intervention, Results, Evidence, Compare.
    - `features/new-intervention/` — product, route, dose, frequency and the four annual
      costs, totalling to a gross cost per patient that says on screen that it is *not* a
      budget impact. Non-negotiable 2 is what an interface erodes first.
    - `features/comparator-import/` and `POST /comparators/import` — .xlsx and .csv
      through one parser, cell-level findings, whole-file rejection, plus a template
      endpoint. M19 sections 5.1–5.6, minus registry writes: an imported row is validated,
      not registered, and reaches a calculation through M12's promotion path so the
      registry stays the single record of what a drug is.
    - `requirements.txt` gained `python-multipart` — FastAPI cannot accept an upload
      without it, and it was missing.

    Three M19 rules are load-bearing here and are tested: every finding carries its sheet
    and cell, all findings return in one pass, and any error rejects the whole file.
    Columns match by label so an inserted column does not shift every value one place.
    28 new tests; 461 passing overall.

    **The one thing worth deciding before writing code:** whether the hackathon demo needs
    Phases 15–17 more than it needs 13–14. The dependency order says subgroups first; a
    judge watching a five-minute demo sees the interface. The order above optimises for a
    tool that stays correct as it grows, which is the right call for a repository and might
    be the wrong one for a deadline. If the deadline wins, build M20 and M21 against the
    current single-population scenario shape and accept that both will need revisiting when
    M18 lands — but decide that deliberately rather than discovering it.
