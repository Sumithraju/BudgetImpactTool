# BIET — Design Diagrams

Thirteen diagrams covering the system as it is built, not as it was planned.
Every box below corresponds to a directory, a module or a table that exists in
this repository. Where a diagram and [`ARCHITECTURE.md`](ARCHITECTURE.md)
disagree, the code was the source.

Diagrams are Mermaid and render on GitHub without a plugin.

| # | Diagram | Answers |
|---|---|---|
| [1](#1-system-context) | System context | Who uses it, what it talks to |
| [2](#2-container--deployment-view) | Container / deployment | What runs where |
| [3](#3-where-the-data-comes-from) | **Data sources → tables** | **Which module the data is from** |
| [4](#4-ingestion-pipeline-m0) | Ingestion pipeline (M0) | How a source row becomes a reference row |
| [5](#5-module-map-m0--m19) | Module map M0–M19 | What the twenty modules are, and their dependency order |
| [6](#6-backend-layer-model) | Backend layer model | The strict layering, and where the engine sits |
| [7](#7-calculation-sequence) | Calculation sequence | What `POST /calculate` actually does |
| [8](#8-value-resolution-chain) | Value resolution chain | How one number gets its value and its provenance |
| [9](#9-engine-dataflow) | Engine dataflow | The arithmetic, module by module |
| [10](#10-database-schema-erd) | Database ERD | The four table groups |
| [11](#11-comparator-intelligence-flow-m11m14) | Comparator intelligence | The only live-at-request-time path |
| [12](#12-frontend-architecture) | Frontend architecture | Slices, steps and result tabs |
| [13](#13-scenario-lifecycle) | Scenario lifecycle | Draft → run → snapshot → export |

---

## 1. System context

```mermaid
flowchart TB
    analyst["<b>P&MA analyst / HEOR</b><br/>builds scenarios, reads results"]
    payer["<b>Budget holder</b><br/>reads the exported deliverable"]

    biet["<b>BIET</b><br/>Budget Impact Estimation Tool<br/><i>React SPA + FastAPI + PostgreSQL/pgvector</i>"]

    subgraph offline["Offline sources — fetched by the ingestion CLI"]
        wb["World Bank Open Data<br/>population, GDP PPP, health exp."]
        who["WHO Global Health Observatory<br/>prevalence + 95% bounds"]
        nadac["NADAC (CMS Medicaid)<br/>US acquisition cost by NDC"]
        fda["openFDA<br/>approval metadata"]
        ct["ClinicalTrials.gov v2<br/>trial / entry context"]
        fx["Frankfurter (ECB)<br/>FX rates"]
        corpus["Guideline corpus<br/>ISPOR · NICE · WHO PDFs"]
    end

    subgraph live["Live — called while serving a request"]
        ot["Open Targets GraphQL"]
        chembl["ChEMBL"]
        reactome["Reactome ContentService"]
    end

    xlsx[("Company workbook<br/>.xlsx / .csv")]

    analyst -->|HTTPS / JSON| biet
    biet -->|PDF · PPTX · XLSX| payer
    analyst -->|uploads| xlsx --> biet

    wb & who & nadac & fda & ct & fx & corpus -.->|"batch, offline"| biet
    biet -->|"per request, M11 only"| ot & chembl & reactome

    classDef sys fill:#1f3a5f,stroke:#0d1f33,color:#fff
    classDef ext fill:#f3f4f6,stroke:#9ca3af,color:#111
    class biet sys
    class wb,who,nadac,fda,ct,fx,corpus,ot,chembl,reactome,xlsx ext
```

**The one asymmetry worth noticing.** Every source except Open Targets,
ChEMBL and Reactome is offline: it is fetched by a CLI, staged, transformed and
published into PostgreSQL, and the API reads only the database. Comparator
discovery (M11) is the single exception — it calls out while serving the
request, which is why it is the only feature that degrades to "could not reach
the drug database" instead of failing the whole tool.

---

## 2. Container / deployment view

```mermaid
flowchart LR
    browser["Browser<br/>localhost:5173"]

    subgraph compose["docker compose"]
        ui["<b>ui</b><br/>nginx + built Vite bundle<br/>:5173<br/><i>Dockerfile.ui</i>"]
        api["<b>api</b><br/>uvicorn · FastAPI<br/>:8077<br/><i>Dockerfile.api</i>"]
        migrate["<b>migrate</b> (one-shot)<br/>alembic upgrade head<br/>+ ingestion --seed-only"]
        db[("<b>db</b><br/>pgvector/pgvector:pg16<br/>:5433 → 5432<br/>volume biet-db")]
    end

    cli["<b>ingestion CLI</b><br/>python -m data.ingestion.run<br/><i>run manually or by cron</i>"]
    ext["Open Targets · Reactome<br/>(HTTP_PROXY passed through)"]

    browser --> ui
    ui -->|"proxy_pass /api/ → api:8077<br/>same origin, no CORS"| api
    api --> db
    migrate -->|"schema + seed, then exits"| db
    cli -->|"--publish"| db
    api -.->|"M11 discovery, live"| ext

    migrate -.->|"service_completed_successfully"| api
    db -.->|"healthcheck pg_isready"| migrate
```

`migrate` is a separate one-shot service rather than an API entrypoint script,
so a failed migration fails visibly instead of leaving an API running against a
schema it does not match.

---

## 3. Where the data comes from

**Short answer: module M0 — Data Foundation & Ingestion, implemented in
`data/`.** Nothing else in the system fetches or parses source data. The API
reads the tables M0 publishes; the engine reads nothing at all.

```mermaid
flowchart LR
    subgraph M0["<b>M0 — Data Foundation &amp; Ingestion</b> · data/"]
        direction TB

        subgraph fetchers["data/ingestion/sources/ — 6 live fetchers"]
            f1["worldbank.py"]
            f2["who_gho.py"]
            f3["nadac.py"]
            f4["frankfurter.py"]
            f5["openfda.py"]
            f6["clinicaltrials.py"]
        end

        subgraph seedcsv["data/seed/ — 22 curated CSVs, every row cited"]
            s1["countries · indications · drugs<br/>drug_regimens · drug_prices · fx_rates"]
            s2["funnel_defaults · eligibility_criteria"]
            s3["adverse_events · adverse_event_costs<br/>drug_adverse_events"]
            s4["disease_subgroups · subgroup_country_rates<br/>subgroup_event_rates · treatment_effects<br/>event_costs · response_profiles<br/>country_health_indicators"]
            s5["aux: ndc_regimen_map · diabetes_cagr<br/>who_country_indicators · who_subgroup_derivation"]
        end

        corpusdir["data/corpus/ — 5 guideline PDFs"]
    end

    subgraph pg["PostgreSQL 16 + pgvector"]
        t1[("country_economics<br/>+ countries.adult_share")]
        t2[("epidemiology<br/>observed + projected")]
        t3[("drug_prices — USA rows")]
        t4[("fx_rates")]
        t5[("staging_extracts<br/>audit trail only")]
        t6[("reference tables<br/>countries · indications · drugs<br/>regimens · prices · funnel_defaults<br/>eligibility_criteria")]
        t7[("safety: adverse_events<br/>adverse_event_costs<br/>drug_adverse_events")]
        t8[("outcomes: disease_subgroups<br/>subgroup_*_rates · treatment_effects<br/>event_costs · response_profiles")]
        t9[("guideline_documents<br/>guideline_chunks (vector 384)")]
    end

    f1 --> t1
    f2 --> t2
    f3 --> t3
    f4 --> t4
    f5 --> t5
    f6 --> t5
    f1 & f2 & f3 & f4 --> t5

    s1 & s2 --> t6
    s3 --> t7
    s4 --> t8
    s1 --> t4
    s5 -.->|"feeds transforms,<br/>owns no table"| f1
    s5 -.-> f2
    s5 -.-> f3

    corpusdir -->|"chunk → embed<br/>BAAI/bge-small-en-v1.5"| t9

    pg --> repos["biet_api/repositories/"] --> services["biet_api/services/"] --> engine["biet_engine<br/><i>pure — reads nothing</i>"]
```

### Source register — what each source supplies and where it lands

| Source | Module / file | Publishes to | On the calculation path? |
|---|---|---|---|
| World Bank Open Data | M0 · `sources/worldbank.py` | `country_economics`, derived `countries.adult_share` | **Yes** — population and affordability denominators |
| WHO GHO | M0 · `sources/who_gho.py` | `epidemiology` (observed + projected row) | **Yes** — prevalence and the PSA interval |
| NADAC | M0 · `sources/nadac.py` | `drug_prices` (USA, via `ndc_regimen_map.csv`) | **Yes** — insulin and generic comparators only |
| Frankfurter (ECB) | M0 · `sources/frankfurter.py` | `fx_rates` | **Yes** — reporting-currency conversion |
| openFDA | M0 · `sources/openfda.py` | `staging_extracts` only | No — metadata |
| ClinicalTrials.gov | M0 · `sources/clinicaltrials.py` | `staging_extracts` only | No — entry context (M14 reads the registry, not this) |
| Curated seed | M0 · `data/seed/*.csv` → `publish/seed.py` | 17 reference/safety/outcome tables | **Yes** — branded prices, funnel defaults, trial effects |
| Guideline PDFs | M0 · `data/corpus/` → `publish/corpus.py` | `guideline_chunks` | No — retrieval grounding for M10 |
| Open Targets / ChEMBL | **M11** · `repositories/comparator.py` | nothing — returned live | Only via M12 promotion |
| Reactome | **M11** · `repositories/comparator.py` | nothing — returned live | Score contribution only |
| Company workbook | **M19** · `services/workbook_service.py` | nothing — becomes editable inputs | Yes, once the user accepts them |

Three things follow from this table, and they are the answers people usually
want:

1. **Branded incretin prices are not from NADAC.** Filtering the 1.5M-row NADAC
   extract to these classes yields 1,204 rows — 1,174 insulin, 30 generic
   liraglutide, zero semaglutide, zero tirzepatide. Branded pricing is curated
   seed (`data/seed/drug_prices.csv`), each row citing a list-price reference
   and a stated gross-to-net assumption.
2. **Nothing imported is saved.** A workbook import lands in the left-hand panel
   as editable values marked as coming from your file; the seeded default stays
   underneath anything the file did not cover.
3. **Every published row carries `source` and `confidence_tier`.** That is a
   contract test, not a convention.

---

## 4. Ingestion pipeline (M0)

```mermaid
flowchart LR
    A["<b>extract</b><br/>Fetcher.fetch()<br/>→ data/raw/"]
    B["<b>validate</b><br/>schema + range assertions<br/>SourceValidationError"]
    C["<b>normalise</b><br/>ISO 3166-1 alpha-3<br/>ISO 4217 · snake_case"]
    D["<b>stage</b><br/>staging_extracts<br/>raw JSONB, unmodified"]
    E["<b>transform</b><br/>WHO filters · latest-non-null<br/>NDC → annual cost"]
    F["<b>publish</b><br/>transactional upsert<br/>on the natural key"]

    A --> B --> C --> D --> E --> F

    F --> G[("reference tables")]
    B -.->|"fails"| X["prior published data<br/>left intact"]

    subgraph props["Properties enforced by test"]
        p1["idempotent — re-running<br/>reproduces the same state"]
        p2["staged — published value traces<br/>back to its source payload"]
        p3["fail-safe — a bad source<br/>never overwrites good data"]
        p4["offline tests — sockets blocked<br/>by an autouse fixture"]
    end
```

Two transform rules carry most of the correctness weight:

- **Latest non-null year, per indicator, per country, independently.** Health
  expenditure lags population by one to two years; a naive join on one fixed
  year silently discards health expenditure — and therefore affordability — for
  every market.
- **Adult share is 18+, not 15+.** The World Bank publishes a 0–14 band; WHO
  prevalence is 18+. Subtracting an approximated 15–17 cohort
  (`pop_0014_pct × 3/15`) removes a 3.2% (DEU) to 6.4% (IND) overstatement of
  the diseased population. The approximation is tier **B**; supplying an
  observed share via `data/seed/age_bands.csv` upgrades it to **A**.

---

## 5. Module map M0 – M19

```mermaid
flowchart TB
    M0["<b>M0</b> Data Foundation<br/>&amp; Ingestion<br/><i>data/</i>"]

    subgraph core["Core budget-impact chain"]
        M1["<b>M1</b> Scenario Workspace"]
        M2["<b>M2</b> Population Funnel"]
        M3["<b>M3</b> Eligibility &amp; Segmentation"]
        M4["<b>M4</b> Uptake &amp; Market Mix"]
        M5["<b>M5</b> Cost &amp; Pricing"]
        M6["<b>M6</b> Persistence &amp; Adherence"]
        M7["<b>M7</b> Budget Impact"]
        M8["<b>M8</b> Affordability &amp; Price Solver"]
        M9["<b>M9</b> Uncertainty &amp; Sensitivity"]
        M10["<b>M10</b> Evidence, Narrative &amp; Export"]
    end

    subgraph comp["Comparator intelligence · Phases 7–11"]
        M11["<b>M11</b> Comparator Discovery"]
        M12["<b>M12</b> Comparator Registry<br/>&amp; Asset Intake"]
        M13["<b>M13</b> Safety &amp; AE Economics"]
        M14["<b>M14</b> Launch-Year Landscape"]
        M15["<b>M15</b> Evidence-Gap Intelligence"]
    end

    subgraph out["Outcomes &amp; payer fit · Phases 12–15"]
        M16["<b>M16</b> Clinical Outcomes<br/>&amp; Avoided Events"]
        M17["<b>M17</b> Payer Perspective<br/>&amp; Decision Views"]
        M18["<b>M18</b> Disease Subgroups"]
        M19["<b>M19</b> Workbook Import"]
    end

    M0 --> M1 & M2 & M5 & M6 & M11
    M2 --> M3 --> M4
    M5 --> M4
    M4 --> M7
    M6 --> M7
    M7 --> M8 --> M9 --> M10
    M7 --> M9
    M9 --> M15
    M11 --> M12 --> M13 & M14
    M13 --> M5
    M14 --> M4
    M2 & M5 & M6 & M7 --> M16 --> M18
    M7 & M8 & M9 --> M17
    M1 & M12 --> M19

    classDef found fill:#1f3a5f,stroke:#0d1f33,color:#fff
    class M0 found
```

**M0 blocks everything** — it is the only module with no upstream dependency
and the only one that writes reference data. **M12 is the hinge** of the
comparator half: until a discovered molecule can be promoted into a priced
comparator, M13 has nothing to attach a safety profile to and M14 has nothing
to admit into a baseline.

### Module → code map

| Module | Engine | API service | Frontend slice |
|---|---|---|---|
| M0 | — | — (offline) | — |
| M1 | — | `scenario_service.py` | `scenario-builder/` |
| M2, M3 | `funnel.py`, `eligibility.py` | `engine_input.py` | `results/tabs/PopulationTab` |
| M4 | `uptake.py` | `engine_input.py` | `scenario-builder/MarketBurden` |
| M5 | `cost.py`, `fx.py` | `pricing_service.py` | `scenario-builder/PriceGrid` |
| M6 | `persistence.py` | `engine_input.py` | `scenario-builder/InputStudio` |
| M7 | `impact.py` | `calculation_service.py` | `results/tabs/SummaryTab`, `WithWithout` |
| M8 | `affordability.py`, `solver.py` | `calculation_service.py` | `affordability/`, `price-solver/` |
| M9 | `sensitivity.py`, `psa.py`, `distributions.py` | `calculation_service.py` | `results/tabs/UncertaintyTab` |
| M10 | `narrative.py` | `narrative_service.py`, `export_service.py` | `evidence/`, `DeliverableTab` |
| M11 | — | `comparator_service.py`, `comparator_classify.py` | `comparator-discovery/` |
| M12 | — | `comparator_registry_service.py` | `ComparatorRegistry.tsx` |
| M13 | `safety.py` | `safety_service.py` | `results/SafetyComparison` |
| M14 | `landscape.py` | `landscape_service.py` | `MarketAccessTab` |
| M15 | `evidence_gap.py` | `evidence_gap_service.py` | `results/EvidencePriority` |
| M16 | `outcomes.py` | `outcomes_service.py` | `results/tabs/OutcomesTab` |
| M17 | — | `payer_service.py` | `results/tabs/PayerTab` |
| M18 | — | `segmentation.py` | `results/tabs/SubgroupsTab` |
| M19 | — | `workbook_service.py`, `excel_service.py` | `scenario-builder/WorkbookPanel` |

---

## 6. Backend layer model

```mermaid
flowchart TB
    subgraph app["biet_api — FastAPI application"]
        R["<b>routes/</b><br/>scenarios · reference · comparators<br/>exports · workbook<br/><i>HTTP surface only</i>"]
        S["<b>services/</b><br/>business logic, value resolution,<br/>transaction boundaries, engine invocation"]
        P["<b>repositories/</b><br/>query composition,<br/>batch loading (no N+1)"]
        D["<b>dal/session.py</b><br/>session &amp; transaction primitives"]
        M["<b>models/</b><br/>SQLAlchemy declarative"]
    end

    E["<b>biet_engine</b><br/>pure calculation package<br/><i>imports no fastapi, sqlalchemy or requests —<br/>asserted by test_layering.py</i>"]

    DB[("PostgreSQL 16<br/>+ pgvector")]

    R --> S --> P --> D --> M --> DB
    S -->|"EngineInput →<br/>← EngineResult"| E

    subgraph schemas["Three Pydantic families, deliberately not shared"]
        s1["<b>schemas/</b> — HTTP contract"]
        s2["<b>engine/models.py</b> — fully resolved,<br/>no optionals, no defaults"]
        s3["<b>models/</b> — persistence structure"]
    end

    classDef pure fill:#14532d,stroke:#052e16,color:#fff
    class E pure
```

**The one line that matters.** The engine receives fully-resolved primitive
values and returns fully-computed results. It never queries, never reads
configuration, never logs outward. That purity is what makes a run
reproducible: replaying a stored snapshot through the recorded engine version
returns the same answer. `backend/tests/test_layering.py` inspects the module
dependency graph and fails if that is ever violated.

---

## 7. Calculation sequence

`POST /api/v1/scenarios/{id}/calculate`

```mermaid
sequenceDiagram
    autonumber
    participant UI as React SPA
    participant RT as routes/scenarios.py
    participant SV as CalculationService
    participant EB as EngineInputBuilder
    participant RS as ResolutionService
    participant RP as repositories/
    participant DB as PostgreSQL
    participant EN as biet_engine (pure)

    UI->>RT: POST /scenarios/{id}/calculate
    RT->>RT: validate payload (Pydantic)
    RT->>SV: calculate(scenario)
    SV->>EB: build_input(scenario)

    EB->>RP: batch-load reference rows
    RP->>DB: SELECT (one query per parameter family)
    DB-->>RP: rows
    RP-->>EB: ResolutionContext

    loop every parameter × market
        EB->>RS: resolve(path, country)
        RS-->>EB: Valued(value, low, high, Provenance)
    end

    Note over EB,RS: scenario override ▸ country override ▸ global default<br/>provenance travels with the value either way

    EB-->>SV: EngineInput (frozen) + warnings

    SV->>EN: run(EngineInput)
    Note right of EN: funnel → eligibility → uptake →<br/>persistence → cost → impact →<br/>affordability → outcomes<br/><b>no I/O of any kind</b>
    EN-->>SV: EngineResult (frozen)

    SV->>DB: INSERT model_runs<br/>(input_snapshot, fx_snapshot, results,<br/>engine_version, duration_ms)
    SV-->>RT: CalculationResponse
    RT-->>UI: 200 — results + provenance + warnings
```

Interactive edits re-enter at step 1 through a 250 ms trailing debounce, with
request cancellation on supersession. Server-side calculation stays the single
source of truth — mirroring the engine in TypeScript would mean two
implementations of the same arithmetic, and they would diverge.

---

## 8. Value resolution chain

Every model input resolves through three ordered levels; the most specific
level present wins, and the interface always shows which one supplied the value
in force.

```mermaid
flowchart TB
    Q["Need: funnel.diagnosis_rate for DEU"]

    Q --> L3{"scenario_overrides<br/>(scenario_id, path, country)?"}
    L3 -->|hit| R3["<b>SCENARIO_OVERRIDE</b><br/>tier C — an asserted value,<br/>not an observed one"]
    L3 -->|miss| L2{"country default<br/>(path, country)?"}
    L2 -->|hit| R2["<b>COUNTRY_OVERRIDE</b><br/>tier as published"]
    L2 -->|miss| L1{"global default<br/>(path, NULL)?"}
    L1 -->|hit| R1["<b>GLOBAL_DEFAULT</b><br/>indication-level seed"]
    L1 -->|miss| ERR["UnresolvedParameterError<br/>→ HTTP 422 naming the parameter"]

    R1 & R2 & R3 --> V["<b>Valued</b><br/>value · low · high<br/>+ Provenance(source, vintage_year,<br/>confidence_tier, resolution_level,<br/>is_projected, note)"]

    V --> W{"launch_year − vintage_year > 5<br/>or is_projected?"}
    W -->|yes| WARN["Warning_ STALE_VINTAGE"]
    W --> ENG["EngineInput — frozen.<br/>Past this point nothing is<br/>looked up, defaulted or inferred."]

    subgraph tiers["Confidence tiers, carried on every value"]
        A["<b>A</b> published, country-specific,<br/>with a stated interval"]
        B["<b>B</b> published, regional<br/>or extrapolated"]
        C["<b>C</b> analogue-derived<br/>or expert assumption"]
        Dd["<b>D</b> placeholder<br/>requiring replacement"]
    end
```

M15 multiplies this tier by M9's swing: a large swing on a tier-A source is
settled; a large swing on a tier-D placeholder is the reason the answer cannot
yet be trusted, and is what turns an uncertainty analysis into a research plan.

---

## 9. Engine dataflow

```mermaid
flowchart TB
    IN["<b>EngineInput</b><br/>every value resolved, frozen,<br/>provenance attached"]

    IN --> F

    subgraph funnel["M2 · funnel.py — the canonical structure"]
        F["total population"] --> F2["× adult_share → adult"]
        F2 --> F3["× prevalence → diseased"]
        F3 --> F4["× diagnosis_rate → diagnosed"]
        F4 --> F5["× treatment_rate → treated"]
        F5 --> F6["× Π criteria → label-eligible"]
        F6 --> F7["× access_rate → <b>addressable</b>"]
    end

    ELIG["<b>M3 · eligibility.py</b><br/>ordered multiplicative stack —<br/>BMI · comorbidity · HbA1c · age<br/>line of therapy · prior failure<br/><i>each toggleable, each overridable</i>"]
    ELIG -.->|"supplies Π criteria"| F6

    F7 --> U["<b>M4 · uptake.py</b><br/>linear · logistic · manual<br/>+ source-of-business vector"]
    U --> PER["<b>M6 · persistence.py</b><br/>f = (1 − p₁₂) / (−ln p₁₂)<br/>patients → patient-years"]

    COST["<b>M5 · cost.py</b><br/>acquisition (dose × schedule<br/>× wastage × discount)<br/>+ admin + monitoring + AE<br/>− offsets · PPP derivation"]
    SAF["<b>M13 · safety.py</b><br/>Σ P(AE) × Cost(AE)"] --> COST
    OUT["<b>M16 · outcomes.py</b><br/>events avoided × event_costs"] -->|"cost offset,<br/>never a separate line"| COST
    LS["<b>M14 · landscape.py</b><br/>pipeline entrants from<br/>expected entry year"] --> U

    PER --> IMP
    COST --> IMP

    IMP["<b>M7 · impact.py</b><br/>cost_with − cost_without<br/>per market, per year<br/>→ FX → reporting currency"]

    IMP --> AFF["<b>M8 · affordability.py</b><br/>impact ÷ health expenditure<br/>→ threshold band"]
    IMP --> SOL["<b>M8 · solver.py</b><br/>reverse: max net price<br/>closed-form, bisection fallback<br/>→ <b>price corridor</b>"]
    IMP --> SEN["<b>M9 · sensitivity.py</b><br/>one-way → tornado"]
    IMP --> PSA["<b>M9 · psa.py</b><br/>Monte Carlo, seeded<br/>WHO bounds → distributions"]
    SEN --> EG["<b>M15 · evidence_gap.py</b><br/>swing × weakness → priority"]

    AFF & SOL & SEN & PSA & OUT & EG --> RES["<b>EngineResult</b><br/>frozen"]

    classDef stage fill:#eef2ff,stroke:#6366f1,color:#111
    class F,F2,F3,F4,F5,F6,F7 stage
```

The funnel is never collapsed into a single pre-computed "eligible population"
figure — the visibility of the intermediate stages is what makes the estimate
defensible.

---

## 10. Database schema (ERD)

```mermaid
erDiagram
    COUNTRIES ||--o{ COUNTRY_ECONOMICS : has
    COUNTRIES ||--o{ EPIDEMIOLOGY : has
    COUNTRIES ||--o{ DRUG_PRICES : has
    COUNTRIES ||--o{ ADVERSE_EVENT_COSTS : has
    COUNTRIES ||--o{ EVENT_COSTS : has
    COUNTRIES ||--o{ SUBGROUP_COUNTRY_RATES : has
    COUNTRIES ||--o{ COUNTRY_HEALTH_INDICATORS : has

    INDICATIONS ||--o{ EPIDEMIOLOGY : scopes
    INDICATIONS ||--o{ FUNNEL_DEFAULTS : scopes
    INDICATIONS ||--o{ ELIGIBILITY_CRITERIA : scopes
    INDICATIONS ||--o{ DRUGS : scopes
    INDICATIONS ||--o{ DISEASE_SUBGROUPS : scopes
    INDICATIONS ||--o{ SCENARIOS : scopes
    INDICATIONS ||--o{ COMPARATOR_ASSETS : scopes

    DRUGS ||--o{ DRUG_REGIMENS : has
    DRUGS ||--o{ DRUG_PRICES : has
    DRUGS ||--o{ DRUG_ADVERSE_EVENTS : has
    DRUGS ||--o{ TREATMENT_EFFECTS : has
    DRUGS ||--o{ RESPONSE_PROFILES : has
    DRUGS ||--o| COMPARATOR_ASSETS : "promoted from"

    ADVERSE_EVENTS ||--o{ ADVERSE_EVENT_COSTS : priced_by
    ADVERSE_EVENTS ||--o{ DRUG_ADVERSE_EVENTS : observed_in

    DISEASE_SUBGROUPS ||--o{ SUBGROUP_EVENT_RATES : has
    DISEASE_SUBGROUPS ||--o{ SUBGROUP_COUNTRY_RATES : has

    SCENARIOS ||--o{ SCENARIO_OVERRIDES : carries
    SCENARIOS ||--o{ MODEL_RUNS : produces
    SCENARIOS ||--o| SCENARIOS : "cloned from"

    COMPARATOR_ASSETS ||--o{ COMPARATOR_APPROVALS : has

    GUIDELINE_DOCUMENTS ||--o{ GUIDELINE_CHUNKS : chunked_into

    COUNTRIES {
        char3 country_code PK
        text currency_code
        numeric adult_share "derived, 18+"
        text adult_share_source
        char adult_share_confidence_tier
        bool is_active
    }
    EPIDEMIOLOGY {
        int id PK
        char3 country_code FK
        int indication_id FK
        smallint year
        numeric prevalence_pct
        numeric prevalence_low "WHO 95% bound"
        numeric prevalence_high
        bool is_projected
        char confidence_tier
    }
    DRUG_PRICES {
        int price_id PK
        int drug_id FK
        char3 country_code FK
        numeric price_local
        text price_basis "list|nadac|estimated_net|ppp_derived"
        numeric gross_to_net_pct
        text source_url
        char confidence_tier
    }
    SCENARIOS {
        uuid scenario_id PK
        int indication_id FK
        text asset_name
        smallint launch_year
        smallint horizon_years
        char3[] country_codes
        text perspective
        bigint covered_population
        text[] subgroup_codes
        uuid parent_scenario_id FK
        bool is_baseline
        bool is_archived
    }
    SCENARIO_OVERRIDES {
        int id PK
        uuid scenario_id FK
        char3 country_code "NULL = all markets"
        text parameter_path
        jsonb value
        text note
    }
    MODEL_RUNS {
        uuid run_id PK
        uuid scenario_id FK
        text engine_version "semantic, frozen"
        jsonb input_snapshot
        jsonb fx_snapshot
        jsonb results
        int duration_ms
    }
    COMPARATOR_ASSETS {
        int asset_id PK
        text source_id "ChEMBL id"
        text target_symbol
        text mechanism_of_action
        text[] pathway_ids "Reactome"
        text competitor_class
        numeric relevance
        int expected_entry_year
        int drug_id FK "set on promotion"
        bool is_new_asset
    }
    GUIDELINE_CHUNKS {
        int chunk_id PK
        int document_id FK
        text chunk_text
        vector embedding "384-dim, ivfflat"
    }
    STAGING_EXTRACTS {
        int id PK
        text source_id
        int row_index
        jsonb payload "raw, unmodified"
        timestamptz fetched_at
    }
```

Four logical groups: **reference** (published by M0), **scenario** (written by
M1), **knowledge** (the embedded corpus), and **comparator** (M11/M12).
`staging_extracts` stands apart — it is the audit trail from any published value
back to the source payload it came from, and nothing reads it at request time.

---

## 11. Comparator intelligence flow (M11→M14)

```mermaid
sequenceDiagram
    autonumber
    participant UI as ComparatorDiscovery.tsx
    participant API as routes/comparators.py
    participant CS as ComparatorService (M11)
    participant OT as Open Targets GraphQL
    participant RE as Reactome
    participant CL as comparator_classify.py (pure)
    participant REG as RegistryService (M12)
    participant DB as PostgreSQL

    UI->>API: GET /comparators/discover?target=GLP1R&indication_id=1
    API->>CS: discover(target, indication)
    CS->>OT: knownDrugs(target) + ChEMBL ids
    alt upstream unreachable
        OT--xCS: timeout / 5xx
        CS-->>UI: UpstreamUnavailableError<br/>"could not reach the drug database"<br/><i>rest of the tool keeps working</i>
    end
    OT-->>CS: molecules, MoA, max clinical phase
    opt include_pathway
        CS->>RE: UniProt → pathways → participants
        RE-->>CS: pathway ids (score contribution only —<br/>never promotes to "direct" on its own)
    end
    CS->>DB: match against seeded drugs
    CS->>CL: classify + deduplicate + rank
    CL-->>CS: direct | therapeutic | pipeline, with rationale
    CS-->>UI: ranked candidates

    UI->>API: POST /comparators/assets — curate
    API->>REG: brand, manufacturer, line, approvals
    REG->>DB: INSERT comparator_assets

    UI->>API: POST /comparators/assets/{id}/promote
    REG->>DB: INSERT drugs + drug_regimens + drug_prices
    Note over REG,DB: a discovered molecule has no price, regimen or<br/>persistence — no public target database carries them.<br/>Promotion is where discovery meets M5.

    REG-->>UI: usable comparator
    Note over UI: unpromoted → visible, flagged, and rejected at<br/>scenario build. A comparator that vanishes understates<br/>the world-without and overstates budget impact.
```

M14 reads `comparator_assets.expected_entry_year` to admit pipeline entrants
into the baseline mix from their entry year. It is **off by default**: every
entrant's price is an assumption, so it is tier-D by construction, warned about,
and belongs in a scenario variant rather than the base case.

---

## 12. Frontend architecture

```mermaid
flowchart TB
    subgraph app["app/"]
        A1["App.tsx — shell, step gating"]
        A2["styles.css"]
    end

    subgraph features["features/ — a slice may not import another slice's internals"]
        direction TB
        S1["<b>scenario-builder/</b><br/>ScenarioForm · InputStudio · PriceGrid<br/>MarketBurden · WorkbookPanel"]
        S2["<b>comparator-discovery/</b><br/>ComparatorDiscovery · ComparatorRegistry"]
        S3["<b>results/</b><br/>ResultsView · 9 tabs · CostBridge<br/>WithWithout · SafetyComparison<br/>EvidencePriority · Interpretation"]
        S4["<b>affordability/</b> AffordabilityGauge"]
        S5["<b>price-solver/</b> PriceCorridor"]
        S6["<b>scenario-compare/</b>"]
        S7["<b>evidence/</b>"]
    end

    subgraph shared["shared/ — may not import any feature"]
        H1["api.ts — typed client + ApiError"]
        H2["format.ts · ui.tsx"]
        H3["ChartFrame.tsx · BrandMark.tsx"]
        H4["useStickyHeader.ts"]
    end

    A1 --> S1 & S2 & S3 & S4 & S5 & S6 & S7
    S1 & S2 & S3 & S4 & S5 & S6 & S7 --> shared
    H1 -->|"/api/v1/*"| API["FastAPI"]
```

### The four steps, in dependency order

```mermaid
flowchart LR
    B["<b>1 · Build</b><br/>who and where<br/><i>markets, disease, subgroup</i>"]
    P["<b>2 · Prices</b><br/>what it costs<br/><i>price grid, workbook import</i>"]
    C["<b>3 · Comparators</b><br/>what it displaces<br/><i>discovery, promotion</i>"]
    R["<b>4 · Results</b><br/>what it means<br/><i>read-only</i>"]

    B --> P --> C --> R

    R --> T1["Population funnel"] & T2["Affordability"] & T3["Market access"] & T4["Budget impact"] & T5["What it buys"]
    R --> T6["Subgroups"] & T7["Payer view"] & T8["Uncertainty"] & T9["Report"]
```

The order is the arithmetic: budget impact is **incremental** — world-with minus
world-without — so the world-without has to be complete before the subtraction
means anything. You cannot build a comparator basket before you know which
markets are in scope, you cannot compare against a therapy that has no price,
and a result computed before either is a result about the wrong world.

---

## 13. Scenario lifecycle

```mermaid
stateDiagram-v2
    [*] --> Draft: POST /scenarios
    Draft --> Draft: PATCH · PUT /overrides<br/>(validated against the closed vocabulary)
    Draft --> Draft: POST /workbook/import<br/>(M19 — nothing saved until accepted)

    Draft --> Calculated: POST /calculate
    Calculated --> Snapshotted: INSERT model_runs<br/>input + fx + results + engine_version

    Snapshotted --> Analysed: GET /owsa · /psa<br/>/solve · /break-even<br/>/uptake-scenarios · /evidence-gaps
    Analysed --> Delivered: GET /narrative<br/>/export.pdf · .pptx · .xlsx

    Calculated --> Draft: edit an assumption<br/>(250 ms debounce, request cancelled on supersession)

    Draft --> Cloned: POST /scenarios/{id}/clone
    Cloned --> Draft: inherits every assumption

    Draft --> Baseline: POST /scenarios/{id}/baseline
    Baseline --> Compared: POST /scenarios/compare<br/>(2–4 side by side)

    Draft --> Archived: DELETE (soft)
    Archived --> [*]

    note right of Snapshotted
        Immutable. Replaying this snapshot
        through the recorded engine version
        returns the same answer — which is
        what the engine's purity buys.
    end note
```

---

## Reading these against the code

| Diagram | Read alongside |
|---|---|
| 3, 4 | `data/ingestion/`, `docs/modules/M0-data-foundation.md` |
| 6 | `backend/tests/test_layering.py` — the layering is enforced, not documented |
| 7, 8 | `services/engine_input.py`, `services/resolution.py` |
| 9 | `backend/src/biet_engine/`, `backend/tests/engine/golden/` |
| 10 | `backend/src/biet_api/models/`, `backend/alembic/versions/` |
| 11 | `services/comparator_service.py`, `repositories/comparator.py` |
| 12 | `frontend/src/app/App.tsx`, `features/results/ResultsView.tsx` |
