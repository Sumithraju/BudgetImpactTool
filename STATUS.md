# BIET — Current Status

**Last updated:** 2026-08-23 · **Phase:** 1 of 5 (Data Foundation) · **Deadline:** 2026-09-06

Read this first when resuming. It is the handoff document; everything else is reference.

---

## 1. Resuming on another machine

### 1.1 Move the project first — it is NOT under version control

`git init` has never been run here. Do this before anything else, or the work cannot be moved
safely.

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
./.venv/bin/python -m data.ingestion.run
```

Expect `6/6 sources succeeded`. Takes a few minutes; NADAC is a 124 MB download. Add
`--no-extract` to re-run transforms against payloads already in `data/raw/`.

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
│   ├── ingestion/               <- ALL PHASE 1 WORK IS HERE (1,148 lines)
│   │   ├── config.py            pydantic-settings; optional proxy
│   │   ├── constants.py         markets, indicators, thresholds — no literals elsewhere
│   │   ├── errors.py            exception hierarchy
│   │   ├── http.py              retry + backoff client
│   │   ├── base.py              Fetcher contract
│   │   ├── run.py               CLI entry point
│   │   ├── sources/             six fetchers
│   │   ├── transform/           EMPTY — publish-stage transforms not written
│   │   ├── publish/             EMPTY — blocked, see §5
│   │   └── tests/               33 tests, offline (313 lines)
│   ├── seed/                    EMPTY — curated CSVs not written yet
│   ├── raw/                     gitignored; regenerate with the CLI
│   └── corpus/                  EMPTY — guideline PDFs not yet ingested
│
├── backend/                     EMPTY — Phase 2
├── frontend/                    EMPTY — Phase 3
└── BI_REPO/                     reference only; see §6
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

## 5. Phase 1 status

### Done

- **Secrets and config.** `pydantic-settings`, `.env.example`, `.gitignore`. Proxy fully optional;
  all six endpoints verified reachable without one.
- **Six source fetchers**, each with `extract → validate → transform`. Raw payloads written to disk
  unmodified, so transforms never touch the network.
- **WHO's four mandatory filters** (`apply_who_filters`) — drops income-group aggregates, region
  aggregates, single-sex series, non-adult age bands. Without these, aggregates load as markets.
- **Latest-non-null-year resolution**, per indicator per country independently. Population and GDP
  reach 2025; health expenditure lags to 2023/2024 with null 2025 rows present. A fixed-year join
  silently discards health expenditure for every market.
- **Adult-share derivation with the 15–17 correction** — see §7.
- **NADAC** current-file resolution by walking Wednesdays backwards, plus dedupe by NDC keeping the
  latest effective date. Scans 1.5 M rows in 2.7 s.
- **FX** with the USD identity row so M7 can pivot every conversion through USD without a special case.
- **CLI runner** (`python -m data.ingestion.run`).
- **33 offline tests**, with an autouse fixture in `conftest.py` that makes any socket call a hard
  failure — the offline guarantee is enforced, not assumed.

Last verified run: `6/6 sources succeeded` — worldbank 50 rows, who_gho 30, nadac 28, openfda 69,
clinicaltrials 200, frankfurter 7.

### Remaining in Phase 1

1. **Seed CSVs** in `data/seed/` — ten files per M0 §5.6. The important one is `drug_prices.csv`:
   NADAC carries **no branded incretin pricing** (26 insulin + 2 generic liraglutide, zero
   semaglutide, zero tirzepatide), so branded prices must be curated with cited public sources and
   stated gross-to-net assumptions.
2. **Alembic schema** — tables per ARCHITECTURE.md §8. Authorable now; running needs a database.
3. **Publish stage** — `data/ingestion/publish/` is empty. **Blocked**, see §5.1.
4. **Diabetes forward projection** — WHO `NCD_GLUC_04` stops at 2014. Needs `diabetes_cagr.csv`
   and the projection logic, with `is_projected` flagging and a `STALE_VINTAGE` warning.
5. **Guideline corpus** — `data/corpus/` empty; embedding needs pgvector.

### 5.1 Blocker: no database

**PostgreSQL and Docker are both absent from the machine this was developed on.** That blocks the
publish stage, Alembic migrations, and pgvector corpus indexing — everything downstream of
`transform`.

On the new machine, install either:

```bash
brew install postgresql@16 && brew services start postgresql@16
```

or [Postgres.app](https://postgresapp.com), or Docker Desktop. pgvector is also required
(`CREATE EXTENSION vector`). Once one is available, items 2 and 3 above unblock immediately.

---

## 6. Action items for you

1. **Rotate the IBAB account password.** `BI_REPO/datadownload.py`, `download_guidelines.py`,
   `ingests_pdfs_to_pgvector.py` and `app.py` contain it in plaintext. It is in git history, so
   deleting the line is not sufficient — the credential must be changed at the source.
2. **Install PostgreSQL 16 + pgvector** to unblock §5.1.
3. **Decide the diabetes CAGR source** — IDF Diabetes Atlas historical series is the likeliest;
   needs confirming and citing before `diabetes_cagr.csv` can be populated.

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

---

## 8. Next steps, in order

1. `git init` and commit (§1.1).
2. Install PostgreSQL 16 + pgvector.
3. Finish Phase 1: seed CSVs → Alembic schema → publish stage → diabetes projection.
4. **Phase 2 — the calculation engine.** Start with **M6 (Persistence)**: zero dependencies, one
   closed-form function, seven reference values to assert. It is the right warm-up and it is on the
   critical path.
5. Phase 3 — API and core UI. Phase 4 — solver, tornado, PSA. Phase 5 — narrative and export.

Build order and dependencies: [docs/modules/README.md](docs/modules/README.md).

---

## 9. Useful commands

```bash
# tests (offline, no database needed)
./.venv/bin/python -m pytest data/ingestion/tests -q

# full ingestion
./.venv/bin/python -m data.ingestion.run

# re-transform without re-downloading
./.venv/bin/python -m data.ingestion.run --no-extract

# one source, verbose
./.venv/bin/python -m data.ingestion.run who_gho -v

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
