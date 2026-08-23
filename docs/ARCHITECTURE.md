# BIET — Budget Impact Estimation Tool
## Architecture & Design Specification

| | |
|---|---|
| **Document version** | 1.0 |
| **Date** | 2026-08-23 |
| **Status** | Baseline for development |
| **System name** | BIET (Budget Impact Estimation Tool) |
| **Domain** | Pricing & Market Access, Health Economics & Outcomes Research |

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [System Overview](#2-system-overview)
3. [Technology Stack](#3-technology-stack)
4. [Module Architecture](#4-module-architecture)
5. [Calculation Engine Specification](#5-calculation-engine-specification)
6. [Country and Reference Data](#6-country-and-reference-data)
7. [Data Architecture](#7-data-architecture)
8. [Database Schema](#8-database-schema)
9. [Backend Architecture](#9-backend-architecture)
10. [API Specification](#10-api-specification)
11. [Frontend Architecture](#11-frontend-architecture)
12. [AI and Retrieval Subsystem](#12-ai-and-retrieval-subsystem)
13. [Non-Functional Requirements](#13-non-functional-requirements)
14. [Repository Layout](#14-repository-layout)
15. [Delivery Plan](#15-delivery-plan)
16. [Appendix A — Glossary](#appendix-a--glossary)
17. [Appendix B — Default Parameter Values](#appendix-b--default-parameter-values)
18. [Appendix C — Reference Standards](#appendix-c--reference-standards)

---

## 1. Purpose and Scope

### 1.1 Problem Statement

At early development stages — pre-launch, pre-pricing, and frequently pre-Phase III readout — Pricing and Market Access teams must answer affordability and reimbursement questions before a full budget impact model exists. A conventional de novo budget impact model requires six to twelve weeks of health-economist time and a settled price, label, and comparator basket. None of these are available at the point where portfolio and pricing decisions are actually made.

BIET closes that gap. It produces an indication-specific, multi-country, ISPOR-aligned budget impact estimate in minutes rather than weeks, operating explicitly under uncertainty and making every assumption traceable to a source and a confidence grade.

### 1.2 Objectives

| # | Objective |
|---|---|
| O1 | Estimate the incremental budget impact of introducing a new therapy, per country, over a launch-relative time horizon |
| O2 | Derive the eligible patient population through a transparent, stage-by-stage epidemiological funnel |
| O3 | Express budget impact as an affordability position against national health expenditure |
| O4 | Solve the inverse problem: given an affordability ceiling, return the maximum defensible price |
| O5 | Quantify uncertainty through deterministic sensitivity and probabilistic simulation, and identify which assumptions dominate the result |
| O6 | Ground every output in cited ISPOR, NICE and WHO methodological guidance |
| O7 | Record every input with its provenance, vintage and confidence tier |

### 1.3 In Scope

- Epidemiological (top-down) budget impact estimation for chronic disease indications
- Cardiometabolic therapy areas: **obesity** and **type 2 diabetes**
- Ten markets spanning high-, upper-middle- and lower-middle-income health systems
- Incremental budget impact — world-with versus world-without comparison
- Persistence- and wastage-adjusted cost of therapy
- Reverse price solving against an affordability threshold
- One-way deterministic sensitivity and probabilistic sensitivity analysis
- Scenario definition, persistence and side-by-side comparison
- Retrieval-augmented narrative generation with source citations
- Export to PDF and PowerPoint

### 1.4 Out of Scope

The following are deliberately excluded. They are recorded here so that scope discipline is auditable.

| Excluded | Rationale |
|---|---|
| HTA submission-grade dossier output | BIET is a decision-triage instrument, not a regulatory submission artefact. Submission models remain de novo builds. |
| Cost-effectiveness analysis, QALYs, ICERs | Different decision question, different methodology, different evidence requirements. |
| Markov cohort or patient-level microsimulation | Budget impact over a 3–5 year horizon does not require state-transition modelling. |
| Payer-facing or field deployment | Internal decision support only. No compliance gating, CRM integration, or content-lock workflow. |
| Machine-learned budget impact prediction | Budget impact is deterministic arithmetic over stated assumptions, not a supervised learning problem. Uncertainty is handled by probabilistic sensitivity analysis, which is the method recognised by ISPOR. |
| Licensed commercial data integration (IQVIA, Optum, Symphony) | Procurement and licensing exceed the delivery window. All data sources are public and openly licensed. |
| Claims-based (bottom-up) population derivation | The epidemiological approach is the primary method. Claims-based estimation is a future extension. |
| Multi-tenancy, SSO, role-based access control | Single-organisation internal deployment. |

### 1.5 Target Users

| Persona | Primary need |
|---|---|
| Market Access Lead | Country-by-country reimbursement feasibility and affordability positioning |
| Pricing Strategist | Maximum defensible price per market; price corridor across markets |
| Health Economist / HEOR | Methodological rigour, assumption traceability, sensitivity structure |
| Portfolio / Product Manager | Rapid go/no-go signal and comparative view across indication scenarios |
| Commercial Strategy | Peak-year budget exposure and uptake sensitivity |

### 1.6 Design Principles

1. **Incremental by construction.** Budget impact is the difference between two worlds, never the gross cost of the new therapy.
2. **The engine is pure.** All calculation logic resides in a dependency-free package with no I/O, no database access and no framework coupling. It is deterministic and independently testable.
3. **Every number carries provenance.** Value, source, vintage year and confidence tier travel together through the entire system.
4. **Defaults are seeds, never constraints.** Every seeded value is overridable at scenario level, and the interface always shows which resolution level supplied the value in force.
5. **Uncertainty is a first-class output.** A point estimate without its sensitivity structure is an incomplete answer.
6. **Reproducibility is enforced by snapshot.** Every model run persists its complete input payload, engine version and foreign-exchange rates, so that any historical result can be regenerated exactly.

---

## 2. System Overview

### 2.1 Logical Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION                                                           │
│  React 18 + Vite + TypeScript — feature-sliced SPA                      │
│  Scenario Builder │ Funnel │ Results │ Sensitivity │ Price Solver │ Copilot│
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ HTTPS / JSON (OpenAPI 3.1 contract)
┌────────────────────────────────▼────────────────────────────────────────┐
│  APPLICATION — FastAPI                                                  │
│                                                                          │
│   routes ──► controllers ──► services ──► repositories ──► DAL          │
│                                  │                                       │
│                                  ▼                                       │
│              ┌───────────────────────────────────────┐                  │
│              │  biet_engine  (pure Python package)   │                  │
│              │  ───────────────────────────────────  │                  │
│              │  funnel · uptake · persistence · cost │                  │
│              │  impact · affordability · solver      │                  │
│              │  sensitivity · psa                    │                  │
│              └───────────────────────────────────────┘                  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│  DATA — PostgreSQL 16 + pgvector                                        │
│  Reference (countries, epidemiology, drugs, prices, economics)          │
│  Scenarios (definitions, overrides, run snapshots, results)             │
│  Knowledge (guideline chunks + 384-dim embeddings)                      │
└─────────────────────────────────────────────────────────────────────────┘
                                 ▲
┌────────────────────────────────┴────────────────────────────────────────┐
│  INGESTION (offline, scheduled)                                         │
│  World Bank · WHO GHO · NADAC · openFDA · ClinicalTrials.gov ·          │
│  Frankfurter FX · Curated price seed · Guideline PDF corpus             │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Request Lifecycle

1. User composes a scenario in the browser: indication, markets, launch year, horizon, price assumption, uptake curve, eligibility criteria, comparator mix.
2. The client `POST`s the scenario to `/api/v1/scenarios/{id}/calculate`.
3. The controller validates the payload against Pydantic schemas and delegates to `ScenarioService`.
4. `ScenarioService` resolves every input through the three-level chain (global default → country override → scenario override), assembling a fully-materialised `EngineInput` object.
5. The pure engine executes and returns an `EngineResult`. No database access occurs during execution.
6. The service persists an immutable run snapshot: input payload, engine semantic version, FX rate set, and results.
7. The response returns to the client, which renders funnel, per-country impact, affordability gauge and tornado.

### 2.3 Separation of Concerns

The boundary between the application layer and the engine is the most important architectural line in the system. The engine receives fully-resolved primitive values and returns fully-computed results. It never queries, never reads configuration, never logs to external systems and never depends on FastAPI, SQLAlchemy or any framework. This makes it unit-testable in isolation, reusable by batch and command-line runners, and — critically — verifiable against reference worked examples.

---

## 3. Technology Stack

### 3.1 Backend

| Concern | Selection | Version | Rationale |
|---|---|---|---|
| Language | Python | 3.12 | Ecosystem alignment with scientific and health-economic tooling |
| Web framework | FastAPI | 0.115+ | Native async, automatic OpenAPI generation, Pydantic-integrated validation |
| Validation / serialisation | Pydantic | v2 | Single source of truth for types across API and engine boundaries |
| ORM | SQLAlchemy | 2.0 | Mature, explicit, supports the repository pattern cleanly |
| Migrations | Alembic | 1.13+ | Versioned, reversible schema evolution |
| Numerics | NumPy | 2.x | Vectorised Monte Carlo simulation |
| ASGI server | Uvicorn | 0.30+ | Standard production ASGI runtime |
| Testing | pytest, pytest-cov, hypothesis | current | Unit, property-based and golden-case testing of the engine |
| Export | ReportLab, python-pptx | current | PDF and PowerPoint deliverable generation |
| LLM client | anthropic | current | Narrative and copilot generation |
| Embeddings | fastembed (BAAI/bge-small-en-v1.5) | current | 384-dimension local embeddings, no external inference dependency |

### 3.2 Frontend

| Concern | Selection | Rationale |
|---|---|---|
| Framework | React 18 + TypeScript 5 | Component model, strict typing across the API boundary |
| Build | Vite 5 | Fast HMR, native ESM, minimal configuration |
| Routing | React Router 6 | Standard declarative routing |
| Server state | TanStack Query 5 | Caching, deduplication, background refetch for calculation results |
| Client state | Zustand | Lightweight scenario-draft state without Redux ceremony |
| Charts | Recharts + Plotly.js | Recharts for standard charts; Plotly for the choropleth map and tornado |
| Styling | Tailwind CSS 3 | Utility-first, consistent spacing and colour tokens |
| Forms | React Hook Form + Zod | Client-side validation mirroring the server Pydantic schemas |
| API client | openapi-typescript + generated fetch client | Types derived from the server OpenAPI schema; eliminates contract drift |

### 3.3 Frontend Composition Model

The frontend is a **single Vite application organised by feature slice**. Module Federation and runtime composition are explicitly not used: the independent-deployment benefit does not apply to a single-team, single-deployable product, while the costs — shared-dependency version pinning, cross-remote state coordination, duplicated build configuration and degraded type inference across remote boundaries — apply immediately.

Modularity is achieved structurally instead. Each feature slice owns its components, hooks, types and API calls, exposes a single public entry point through an index barrel, and may not import from another slice's internals. Cross-slice dependencies are permitted only on `shared/`. This yields the same isolation and ownership properties as micro-frontends, enforced at build time by ESLint boundary rules, with none of the runtime cost.

### 3.4 Data and Infrastructure

| Concern | Selection | Rationale |
|---|---|---|
| Database | PostgreSQL 16 | Relational integrity for reference data; JSONB for run snapshots |
| Vector store | pgvector 0.7+ | Co-located with relational data; avoids a second datastore |
| Containerisation | Docker + Docker Compose | Reproducible local and demonstration environments |
| Configuration | pydantic-settings + `.env` | Typed configuration; no secrets in source |

### 3.5 Security Baseline

- No credential, API key, proxy string or connection secret is committed to source. All are supplied through environment variables and validated at startup by `pydantic-settings`.
- Network egress proxy configuration is optional and environment-driven; ingestion scripts must operate identically with and without a proxy.
- The `.env` file is git-ignored; `.env.example` documents required keys with placeholder values only.
- Database access uses a least-privilege application role separate from the migration role.

---

## 4. Module Architecture

Ten modules, grouped into calculation, data and presentation concerns.

### M1 — Scenario Workspace

**Responsibility.** Lifecycle management of scenarios: creation, cloning, versioning, comparison and archival.

A scenario is the unit of work. It binds an asset definition (name, molecule class, route of administration, development stage), an indication, a set of target markets, a launch year, a time horizon in launch-relative years, a reporting currency, and the complete set of assumption overrides that distinguish it from seeded defaults.

**Key behaviours.**
- Clone-with-override: derive a new scenario from an existing one, inheriting all assumptions, so that variant analysis costs a single action.
- Baseline locking: designate one scenario as the reference against which others are diffed.
- Comparison: render two to four scenarios side by side across all output dimensions.

### M2 — Population Funnel Engine

**Responsibility.** Derive the addressable patient population for each country and each launch-relative year through an ordered, auditable sequence of stages.

The funnel is the canonical structure of the system. Each stage is a named quantity produced by applying one factor to the preceding stage, and each factor carries its own value, source, vintage and confidence tier. The funnel is never collapsed into a single pre-computed "eligible population" figure, because the visibility of intermediate stages is what makes the estimate defensible.

**Stages.** Total population → adult population → diseased population → diagnosed → treated → label-eligible → access-adjusted addressable.

### M3 — Eligibility and Segmentation

**Responsibility.** Model the narrowing effect of label criteria and clinical positioning.

Eligibility criteria are composed as an ordered stack of multiplicative factors applied at the label-eligible stage. Each criterion is independently toggleable and independently overridable, so the difference between a broad and a narrow label is a visible, quantified step rather than an opaque adjustment.

Supported criterion types: body mass index threshold, comorbidity requirement, glycated haemoglobin threshold, age band, line of therapy, prior therapy failure, and contraindication exclusion.

Criteria are assumed conditionally independent. Where correlation is material — for example between BMI ≥ 35 and established cardiovascular disease — a single combined criterion with an empirically derived joint factor must be used instead of two separate criteria. This constraint is documented in the criterion library and enforced by validation warnings.

### M4 — Uptake and Market Mix

**Responsibility.** Project the share of the addressable population receiving the new therapy in each year, and the corresponding displacement of incumbent therapies.

Two coupled concerns. First, the uptake trajectory: how quickly the new therapy penetrates its addressable population. Three curve families are supported — linear ramp, logistic diffusion, and manually specified year vectors. Second, source of business: from which incumbent therapies the new therapy's patients are drawn, expressed as a substitution vector summing to unity across incumbents plus a treatment-naive expansion component.

The distinction matters materially. A patient switching from a high-cost incumbent contributes only the price differential to budget impact; a treatment-naive patient contributes the full cost of therapy. Systems that ignore source of business overstate budget impact substantially.

### M5 — Cost and Pricing Engine

**Responsibility.** Compute the annual per-patient cost of each therapy in each market.

Composes drug acquisition cost from dose, administration schedule, wastage and discount; adds administration, monitoring and adverse-event management costs; subtracts cost offsets from avoided events. Handles cross-market price derivation where no observed local price exists, through purchasing-power-parity-adjusted differential pricing with an explicit and adjustable income elasticity.

### M6 — Persistence and Adherence

**Responsibility.** Adjust patient headcount to treatment-year equivalents.

A patient who discontinues at month five consumes five months of drug, not twelve. In cardiometabolic therapy — and in the incretin class in particular — real-world twelve-month persistence is materially below unity, and the resulting adjustment is frequently the largest single correction applied to a naive estimate. This module converts patient counts into persistence-adjusted patient-years using a closed-form exponential survival integral.

### M7 — Budget Impact Calculator

**Responsibility.** Execute the incremental world-with versus world-without comparison and aggregate results.

Produces, for each country and each launch-relative year: cost of the world without the new therapy, cost of the world with it, incremental budget impact, incremental impact per treated patient, and cumulative impact across the horizon. Aggregates across countries into the reporting currency using the foreign-exchange snapshot bound to the run.

### M8 — Affordability and Price Solver

**Responsibility.** Position budget impact against payer capacity, and invert the relationship to solve for price.

Forward direction: express budget impact as a proportion of national current health expenditure, and classify against configurable threshold bands.

Reverse direction: given a target affordability ceiling, return the maximum net annual price per patient that satisfies it. Because budget impact is linear in price when all other parameters are held fixed, the solution is closed-form; a bisection fallback handles configurations containing non-linearities such as tiered discount structures or price floors. Executed across all selected markets, this produces a **price corridor** — the market-by-market ceiling that a global pricing strategy must respect.

### M9 — Uncertainty and Sensitivity

**Responsibility.** Quantify the confidence interval around the estimate and rank assumptions by influence.

Two complementary analyses. Deterministic one-way sensitivity varies each input across its plausible range while holding all others at base case, producing a tornado diagram ranked by absolute swing. Probabilistic sensitivity analysis samples all uncertain inputs simultaneously from their assigned distributions across several thousand iterations, producing a full distribution of budget impact with credible intervals and threshold-exceedance probabilities.

Prevalence distributions are parameterised directly from published WHO confidence bounds rather than from assumed variation, which makes the uncertainty statement empirically grounded rather than notional.

### M10 — Evidence, Narrative and Export

**Responsibility.** Ground outputs in methodological guidance and produce distributable deliverables.

Retrieval over a vector-indexed corpus of ISPOR, NICE and WHO budget impact guidance supplies cited passages; a language model composes an executive narrative constrained to the computed results and the retrieved passages. Export renders results, the complete assumption register and the citation list to PDF and PowerPoint.

---

## 5. Calculation Engine Specification

### 5.1 Notation

| Symbol | Meaning |
|---|---|
| `c` | Country index |
| `y` | Launch-relative year, `y ∈ {1 … N}`, where `y = 1` is the launch year |
| `N` | Time horizon in years, default 3, permitted range 1–5 |
| `t` | Therapy index within the comparator set |
| `n` | The new therapy under evaluation |

**Year convention.** All time indices are launch-relative. Year 1 is the launch year; calendar year is derived as `launch_year + y - 1` for display and for indexing time-varying reference data. Launch-relative indexing is used because pre-launch assets have uncertain launch dates, and uptake trajectories are defined relative to market entry rather than to the calendar.

### 5.2 Module M2 — Population Funnel

```
Pop(c,y)        = population_total(c) × (1 + pop_growth(c))^(y-1)
Adult(c,y)      = Pop(c,y) × adult_share(c)
Diseased(c,y)   = Adult(c,y) × prevalence(c, indication)
Diagnosed(c,y)  = Diseased(c,y) × diagnosis_rate(c, indication)
Treated(c,y)    = Diagnosed(c,y) × treatment_rate(c, indication)
Eligible(c,y)   = Treated(c,y) × Π(k ∈ K) criterion_factor(k)
Addressable(c,y)= Eligible(c,y) × access_rate(c)
```

Where `K` is the set of enabled eligibility criteria from M3.

**Denominator alignment constraint.** WHO prevalence indicators `NCD_BMI_30A` (obesity) and `NCD_GLUC_04` (diabetes) are published for the adult population aged 18 and over. World Bank indicator `SP.POP.TOTL` reports total population across all ages. Applying an adult prevalence rate to a total population denominator inflates the diseased population by the paediatric share — approximately 22 percent in high-income markets and approximately 35 percent in India. The `adult_share(c)` factor is therefore mandatory and is derived as `1 - SP.POP.0014.TO.ZS / 100`.

**Access rate.** Represents the proportion of label-eligible patients with reimbursed access under the assumed formulary position. It is distinct from uptake: access defines who *may* receive the therapy, uptake defines what proportion of those actually do.

### 5.3 Module M4 — Uptake Trajectory

**Linear ramp.**
```
u(y) = u₁ + (u_N - u₁) × (y - 1) / max(1, N - 1)
```

**Logistic diffusion.**
```
u(y) = u_max / (1 + exp(-k × (y - y_mid)))
```
where `u_max` is the plateau share, `k` the steepness coefficient (default 1.2), and `y_mid` the inflection year (default `N/2`). Logistic is the default for therapies entering an established competitive class; linear is the default for first-in-class entry into an untreated population.

**Manual.** A user-supplied vector `[u₁, u₂, … u_N]`, validated to lie within `[0, 1]` and to be monotonically non-decreasing unless explicitly flagged as a competitive-erosion scenario.

**Source of business.** The substitution vector `σ` allocates new-therapy patients across their prior treatment state:
```
Σ(t ∈ T) σ_t + σ_naive = 1,      σ_t ≥ 0
```

Resulting incumbent market shares in the world-with case:
```
m_with(t, y) = max(0, m_without(t, y) - u(y) × σ_t)
```

### 5.4 Module M6 — Persistence Adjustment

Let `p₁₂` denote the proportion of patients still on therapy at twelve months. Assuming exponential time-to-discontinuation with hazard `λ`, calibrated so that `S(12) = p₁₂`:

```
λ = -ln(p₁₂) / 12
```

The persistence-adjusted treatment-year fraction is the mean of the survival function over the year:

```
        1   ⌠12  -λm         1 - e^(-12λ)        1 - p₁₂
f  =   ──   ⎮   e     dm  =  ────────────  =  ─────────────
       12   ⌡0                   12λ           -ln(p₁₂)
```

**Closed form:**
```
f = (1 - p₁₂) / (-ln p₁₂)          for 0 < p₁₂ < 1
f = 1                              for p₁₂ = 1  (limiting case)
```

Worked values:

| `p₁₂` | `f` | Interpretation |
|---|---|---|
| 1.00 | 1.000 | Full-year persistence |
| 0.70 | 0.841 | 84.1% of a full treatment-year consumed |
| 0.50 | 0.721 | 72.1% |
| 0.30 | 0.581 | 58.1% |
| 0.20 | 0.497 | 49.7% |

Persistence is applied per therapy, since the new therapy and its comparators may differ materially in discontinuation profile. In steady state beyond year one, the incident cohort is supplemented by the surviving prevalent cohort; for the three-to-five-year horizons in scope, the first-year fraction is applied uniformly and the resulting conservatism is documented as a stated model limitation.

### 5.5 Module M5 — Cost of Therapy

**Annual acquisition cost.**
```
acq(t,c) = unit_price(t,c) × units_per_admin(t) × admins_per_year(t) × (1 + wastage(t)) × (1 - discount(t,c))
```

**Total annual cost per treated patient-year.**
```
AC(t,c) = acq(t,c) + admin_cost(t,c) + monitoring_cost(t,c) + ae_cost(t,c) - offset(t,c)
```

**Cross-market price derivation.** Where no observed price exists for market `c`, the price is derived from a reference market by purchasing-power-parity adjustment with explicit income elasticity:

```
                                     ⎛ gdp_pc_ppp(c)  ⎞ ᵋ
price(c) = max ⎛ price(ref) ×        ⎜ ─────────────── ⎟   ,  floor × price(ref) ⎞
               ⎝                     ⎝ gdp_pc_ppp(ref) ⎠                          ⎠
```

with income elasticity `ε` defaulting to 1.0 and a price floor of 0.05. This is a modelling assumption, not an observation, and is labelled as such wherever a derived price appears in the interface. Both `ε` and the floor are exposed as sensitivity levers, since international reference pricing behaviour varies substantially by market.

### 5.6 Module M7 — Incremental Budget Impact

This is the definitional core of the system.

**World without the new therapy:**
```
Cost_without(c,y) = Addressable(c,y) × Σ(t ∈ T) [ m_without(t,y) × f_t × AC(t,c) ]
```

**World with the new therapy:**
```
Cost_with(c,y) = Addressable(c,y) × [ u(y) × f_n × AC(n,c)
                                     + Σ(t ∈ T) m_with(t,y) × f_t × AC(t,c) ]
```

**Incremental budget impact:**
```
BI(c,y) = Cost_with(c,y) - Cost_without(c,y)
```

Substituting the displacement relation `m_with(t,y) = m_without(t,y) - u(y) × σ_t` yields the reduced form used by the implementation:

```
BI(c,y) = Addressable(c,y) × u(y) × [ f_n × AC(n,c) - Σ(t ∈ T) σ_t × f_t × AC(t,c) ]
```

The bracketed term is the **net incremental cost per patient switched**: the persistence-adjusted cost of the new therapy less the persistence-adjusted weighted cost of the therapies it displaces. Where the new therapy displaces a high-cost incumbent, this term may be negative, and the correct result is a budget *saving*. A model that omits the displacement term reports the gross cost of the new therapy and overstates budget impact by the full cost of displaced care.

**Aggregations.**
```
Cumulative(c)      = Σ(y = 1 … N) BI(c,y)
PerPatient(c,y)    = BI(c,y) / (Addressable(c,y) × u(y))
Total(y)           = Σ(c) BI(c,y) / fx_rate(currency(c) → reporting_currency)
```

Foreign-exchange rates are resolved once at run time and persisted into the run snapshot. Subsequent re-execution of a stored run uses the snapshotted rates, so historical results never change silently as rates move.

### 5.7 Module M8 — Affordability Position

```
HealthBudget(c,y) = health_exp_pc(c) × Pop(c,y)

AffordabilityRatio(c,y) = BI(c,y) / HealthBudget(c,y)
```

Default classification bands, configurable per deployment:

| Band | Ratio of national health expenditure | Interpretation |
|---|---|---|
| Low | < 0.10% | Unlikely to trigger budget-driven access restriction |
| Moderate | 0.10% – 0.50% | Managed entry or risk-sharing arrangement likely required |
| High | 0.50% – 1.00% | Significant reimbursement resistance expected |
| Critical | > 1.00% | Access improbable without substantial price concession or volume cap |

For markets modelled at plan rather than national level, per-member-per-year is reported as `BI(c,y) / covered_lives(c)`.

### 5.8 Module M8 — Reverse Price Solver

Given a target affordability ratio `τ`, solve for the maximum net annual price per patient of the new therapy.

Budget impact is linear in the new therapy's unit price when all other parameters are held fixed. Writing `p` for the reference-market net annual acquisition price and separating terms:

```
BI(c,y) = α(c,y) × p + β(c,y)
```

where:
```
D(c,y)  = Addressable(c,y) × u(y)                                    (patients on new therapy)

α(c,y)  = D(c,y) × f_n × (1 + wastage_n) × (1 - discount_n) × ppp_factor(c)

β(c,y)  = D(c,y) × [ (admin_n + monitoring_n + ae_n - offset_n)  × f_n
                     - Σ(t) σ_t × f_t × AC(t,c) ]
```

Applying the affordability constraint across the full horizon:
```
Σ(y) [ α(c,y) × p + β(c,y) ]  =  τ × Σ(y) HealthBudget(c,y)
```

**Analytic solution:**
```
          τ × Σ(y) HealthBudget(c,y)  -  Σ(y) β(c,y)
p*(c) =  ───────────────────────────────────────────
                      Σ(y) α(c,y)
```

**Fallback.** Where the configuration introduces non-linearity in price — tiered discount schedules or volume-dependent rebates — the analytic form is invalid. The solver detects these conditions and falls back to bisection on `p ∈ [0, 10 × p_ref]` with a relative tolerance of 1×10⁻⁶ and a cap of 100 iterations. The response records which method was used.

An active price floor in the purchasing-power adjustment does **not** require the fallback: since `max(a·p, b·p) = p · max(a, b)` for `p > 0`, the floor acts as a constant multiplier on price and linearity is preserved. The analytic path remains valid.

**Degenerate cases.**
- `Σα = 0` — no patients reach the new therapy in any year. No solution exists; the solver returns unbounded with a diagnostic.
- `p* < 0` — the affordability target cannot be met at any non-negative price, because displaced-therapy savings are insufficient. Returns infeasible with the shortfall quantified.

**Price corridor.** Executing the solver across all selected markets yields the vector `{p*(c)}`. The minimum across markets is the binding constraint for a single global price; the full vector defines the differential pricing envelope. This output directly addresses the pre-launch pricing question that motivates the system.

### 5.9 Module M9 — Sensitivity Analysis

**One-way deterministic.** For each input `x_i` with plausible range `[lo_i, hi_i]`, evaluate total cumulative budget impact at both bounds while holding all other inputs at base case:

```
swing_i = | BI_total(x_i = hi_i) - BI_total(x_i = lo_i) |
```

Inputs are ranked by descending swing and rendered as a tornado diagram. The ranking is the substantive output: it identifies which assumptions determine the answer and therefore which evidence is worth acquiring before the decision is made.

**Probabilistic sensitivity analysis.** Monte Carlo simulation over `M` iterations (default 5,000). Assigned distributions:

| Parameter class | Distribution | Parameterisation |
|---|---|---|
| Prevalence | Beta | Method of moments from WHO published mean and 95% bounds |
| Diagnosis rate, treatment rate, access rate | Beta | From mean and assumed standard error |
| Eligibility criterion factors | Beta | From mean and confidence tier |
| Uptake plateau | Beta | From mean and assumed standard error |
| Twelve-month persistence | Beta | From mean and assumed standard error |
| Unit prices | Triangular | Minimum, mode, maximum from the price scenario range |
| Administration, monitoring, adverse-event costs | Gamma | Shape and scale from mean and standard error |

For any parameter supplied with published bounds, the standard deviation is derived as `(upper - lower) / 3.92`, the normal approximation to a 95 percent interval.

Reported outputs: mean, median, 2.5th and 97.5th percentiles of cumulative budget impact; the probability that budget impact exceeds each affordability band threshold; and a cumulative distribution plot.

**Confidence tiers.** Every parameter carries a tier that determines its default uncertainty width when no published interval exists:

| Tier | Source character | Default relative standard error |
|---|---|---|
| A | Published, country-specific, with stated interval | Interval as published |
| B | Published, regional or extrapolated | 15% |
| C | Analogue-derived or expert assumption | 30% |
| D | Placeholder requiring replacement | 50% |

---

## 6. Country and Reference Data

### 6.1 Market Coverage

Ten markets, selected to span health-system archetypes and income levels.

| ISO3 | Market | Currency | Archetype | Population (2025) | Health exp. per capita (USD) | Vintage | GDP per capita PPP (USD) | National health budget (USD bn) |
|---|---|---|---|---|---|---|---|---|
| USA | United States | USD | Multi-payer, commercial + public | 341.8 M | 13,473 | 2023 | 90,027 | 4,604.9 |
| GBR | United Kingdom | GBP | Single-payer national | 69.5 M | 5,860 | 2024 | 64,606 | 407.2 |
| DEU | Germany | EUR | Statutory sickness fund | 83.5 M | 6,849 | 2024 | 75,407 | 571.9 |
| FRA | France | EUR | Statutory national insurance | 68.7 M | 5,327 | 2024 | 63,975 | 366.1 |
| ITA | Italy | EUR | Regional national health service | 58.9 M | 3,398 | 2024 | 62,803 | 200.2 |
| ESP | Spain | EUR | Regional national health service | 49.4 M | 3,107 | 2023 | 59,868 | 153.3 |
| JPN | Japan | JPY | Universal social insurance | 123.4 M | 3,638 | 2023 | 55,422 | 448.8 |
| CHN | China | CNY | Basic medical insurance, tiered | 1,406.6 M | 763 | 2023 | 29,333 | 1,073.8 |
| BRA | Brazil | BRL | Public SUS + supplementary | 212.8 M | 1,010 | 2023 | 23,433 | 214.9 |
| IND | India | INR | Predominantly out-of-pocket | 1,463.9 M | 85 | 2023 | 11,748 | 124.0 |

Health budget is computed as health expenditure per capita multiplied by population. The three-order-of-magnitude spread in per-capita health expenditure between the United States and India is the principal driver of affordability divergence and is the reason the reverse price solver must operate per market rather than globally.

### 6.2 Foreign Exchange

Rates are sourced from the Frankfurter API against a USD base and cover every currency required by the market set.

| Currency | Units per USD | Markets |
|---|---|---|
| EUR | 0.86386 | DEU, FRA, ITA, ESP |
| GBP | 0.73933 | GBR |
| JPY | 159.70 | JPN |
| CNY | 6.7423 | CHN |
| BRL | 5.2074 | BRA |
| INR | 95.69 | IND |
| USD | 1.00000 | USA |

Rates carry a fetch date and are snapshotted into every run.

### 6.3 Baseline Epidemiology — Obesity

WHO Global Health Observatory indicator `NCD_BMI_30A`, BMI ≥ 30 kg/m², adults aged 18 and over, both sexes, reference year 2024. Confidence bounds are as published and are used directly to parameterise the probabilistic sensitivity analysis.

| ISO3 | Prevalence | 95% lower | 95% upper | Adult share | Adults with obesity |
|---|---|---|---|---|---|
| USA | 40.96% | 38.18% | 43.72% | 0.78 | 109.2 M |
| BRA | 30.14% | 27.42% | 32.96% | 0.78 | 50.0 M |
| GBR | 27.38% | 25.14% | 29.76% | 0.80 | 15.2 M |
| DEU | 20.64% | 17.59% | 23.91% | 0.82 | 14.1 M |
| ESP | 15.31% | 12.47% | 18.43% | 0.85 | 6.4 M |
| ITA | 13.99% | 11.86% | 16.37% | 0.86 | 7.1 M |
| FRA | 11.19% | 9.63% | 12.92% | 0.81 | 6.2 M |
| CHN | 9.29% | 7.86% | 10.82% | 0.82 | 107.2 M |
| IND | 8.01% | 6.99% | 9.18% | 0.65 | 76.2 M |
| JPN | 5.90% | 4.75% | 7.15% | 0.86 | 6.3 M |

Adult counts are computed as population x adult share x prevalence, using the population figures in §6.1 and the adult shares shown. They are reproducible from the table.

### 6.4 Baseline Epidemiology — Type 2 Diabetes

WHO Global Health Observatory indicator `NCD_GLUC_04`, adults aged 18 and over, both sexes.

| ISO3 | Prevalence | 95% lower | 95% upper |
|---|---|---|---|
| CHN | 8.80% | 6.00% | 12.40% |
| IND | 8.70% | 5.90% | 12.00% |
| BRA | 8.30% | 5.30% | 12.10% |
| USA | 7.30% | 5.10% | 10.10% |
| ESP | 7.10% | 4.60% | 10.20% |
| JPN | 6.70% | 4.70% | 9.00% |
| FRA | 5.90% | 3.80% | 8.60% |
| GBR | 5.80% | 4.10% | 7.70% |
| ITA | 5.80% | 3.80% | 8.30% |
| DEU | 5.00% | 3.20% | 7.20% |

**Vintage constraint.** The latest year available from this indicator is **2014**. The series has not been refreshed, and the values above are consequently more than a decade stale in a disease area with documented rising incidence. Two mitigations are mandatory:

1. Forward projection to the model year at a documented compound annual growth rate per market, with the projection explicitly labelled and the underlying vintage displayed.
2. Provision for manual override from the International Diabetes Federation Diabetes Atlas, which publishes current national estimates.

Every diabetes prevalence value surfaced in the interface is tagged with its 2014 vintage and confidence tier B. This limitation is recorded in the model's stated assumptions and in all exported deliverables.

---

## 7. Data Architecture

### 7.1 Source Register

| # | Source | Content | Refresh | Licence | Role |
|---|---|---|---|---|---|
| 1 | World Bank Open Data API | Population, GDP per capita PPP, current health expenditure per capita, out-of-pocket share, age structure | Annual | CC BY 4.0 | Population denominators, affordability denominators |
| 2 | WHO Global Health Observatory | Obesity, overweight and diabetes prevalence with confidence bounds | Irregular | Open | Disease prevalence, PSA distributions |
| 3 | NADAC (CMS Medicaid) | US pharmacy acquisition cost by NDC | Weekly | Public domain | Insulin and generic comparator pricing |
| 4 | Curated price seed | Branded therapy list and estimated net prices with citations | Manual | Internal | Branded incretin and comparator pricing |
| 5 | openFDA Drug Approvals | Approval history, labelling, dosage forms | Daily | Public domain | Asset and comparator metadata |
| 6 | ClinicalTrials.gov API v2 | Active trials in scope | Daily | Public domain | Competitive entry context |
| 7 | Frankfurter API (ECB) | Foreign exchange rates | Daily | Open | Currency conversion |
| 8 | Guideline corpus | ISPOR, NICE and WHO budget impact methodology | Static | Publicly distributed | Retrieval grounding |

### 7.2 Source Data Constraints

These are properties of the source data that the ingestion layer must handle explicitly. Each has been verified against the retrieved datasets.

**WHO Global Health Observatory extracts contain aggregate rows.** The response includes rows where `SpatialDimType` is `WORLDBANKINCOMEGROUP` or `REGION` alongside true country rows. Ingestion must filter to `SpatialDimType = 'COUNTRY'`, or aggregate rows will be loaded as if they were markets.

**WHO extracts are sex- and age-stratified.** The `Dim1` dimension takes values `SEX_MLE`, `SEX_FMLE` and `SEX_BTSX`. Ingestion selects `SEX_BTSX`. The `Dim2` dimension is `AGEGROUP_YEARS18-PLUS` throughout, which establishes the adult denominator requirement in §5.2.

**World Bank indicators have differing latest-available years.** Population and GDP per capita PPP are populated through 2025; current health expenditure per capita lags to 2023 or 2024 depending on market, and 2025 rows are present but null. Ingestion must resolve each indicator to its latest non-null year per country independently, and must record the resolved vintage alongside the value. A naive join on a single fixed year silently discards health expenditure for every market.

**NADAC does not contain branded incretin pricing.** Filtering the full 1.5-million-row NADAC extract to the therapy classes of interest yields 1,204 rows, of which 1,174 are insulin products and 30 are generic liraglutide. There are no semaglutide or tirzepatide rows: NADAC reports pharmacy acquisition cost, which is available principally for multi-source and generic products. Branded incretin pricing must therefore come from the curated price seed table (source 4), with each entry citing a public list-price reference and a stated gross-to-net assumption. NADAC's role is confined to insulin and generic comparator pricing, where it is authoritative.

**NADAC pricing units are heterogeneous.** The `Pricing Unit` field takes values `ML` and `EA`. Converting a per-unit acquisition cost to an annual cost per patient requires an explicit NDC-to-regimen mapping specifying concentration, units per presentation and presentations per year. This mapping is maintained as curated reference data, not inferred.

**openFDA and ClinicalTrials.gov payloads are deeply nested.** The approvals extract embeds serialised JSON in the `submissions` and `products` columns. These sources supply contextual metadata only and are not on the calculation path; they are parsed into flat projections during ingestion and are never read by the engine.

### 7.3 Value Resolution Chain

Every model input resolves through three ordered levels. The interface always displays which level supplied the value in force.

```
1. Global default      — seeded reference value, indication-level
2. Country override    — market-specific reference value
3. Scenario override   — user-supplied value for this scenario only
```

Resolution takes the most specific level present. Provenance metadata — source identifier, vintage year, confidence tier, and any note — travels with the value regardless of the level at which it resolves. This is what makes the seeded library reusable across markets rather than requiring per-country duplication.

### 7.4 Ingestion Pipeline

```
extract  →  validate  →  normalise  →  stage  →  transform  →  publish
```

- **Extract.** Idempotent source-specific fetchers. Network proxy configuration is read from the environment and is optional. Every fetcher retries with backoff and records a fetch timestamp.
- **Validate.** Schema and range assertions per source. A source failing validation does not overwrite the previously published reference data.
- **Normalise.** Country identifiers to ISO 3166-1 alpha-3; currencies to ISO 4217; column names to snake case.
- **Stage.** Raw extracts land in `staging_*` tables preserving source structure without transformation, providing an audit trail from published value back to source payload.
- **Transform.** Apply the filters and resolution rules in §7.2 to produce clean reference rows with provenance.
- **Publish.** Transactional upsert into reference tables. Prior values are retained and superseded rather than deleted.

---

## 8. Database Schema

PostgreSQL 16 with the `vector` extension. Three logical groups: reference, scenario, and knowledge.

### 8.1 Reference Data

```sql
CREATE TABLE countries (
    country_code        CHAR(3) PRIMARY KEY,
    country_name        TEXT NOT NULL,
    currency_code       CHAR(3) NOT NULL,
    region              TEXT,
    health_system_type  TEXT,
    adult_share         NUMERIC(5,4) NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE country_economics (
    id                  BIGSERIAL PRIMARY KEY,
    country_code        CHAR(3) NOT NULL REFERENCES countries(country_code),
    indicator           TEXT NOT NULL,     -- population_total | gdp_pc_ppp
                                           -- health_exp_pc_usd | oop_health_pct
    year                SMALLINT NOT NULL,
    value               NUMERIC NOT NULL,
    source              TEXT NOT NULL,
    confidence_tier     CHAR(1) NOT NULL DEFAULT 'A',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (country_code, indicator, year)
);

CREATE TABLE indications (
    indication_id       SERIAL PRIMARY KEY,
    indication_name     TEXT NOT NULL UNIQUE,
    therapy_area        TEXT NOT NULL,
    icd10               TEXT,
    who_indicator_code  TEXT,
    default_horizon     SMALLINT NOT NULL DEFAULT 3
);

CREATE TABLE epidemiology (
    id                  BIGSERIAL PRIMARY KEY,
    country_code        CHAR(3) NOT NULL REFERENCES countries(country_code),
    indication_id       INT NOT NULL REFERENCES indications(indication_id),
    year                SMALLINT NOT NULL,
    prevalence_pct      NUMERIC(6,3) NOT NULL,
    prevalence_low      NUMERIC(6,3),
    prevalence_high     NUMERIC(6,3),
    age_group           TEXT NOT NULL DEFAULT 'AGEGROUP_YEARS18-PLUS',
    sex                 TEXT NOT NULL DEFAULT 'SEX_BTSX',
    source              TEXT NOT NULL,
    confidence_tier     CHAR(1) NOT NULL,
    is_projected        BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (country_code, indication_id, year, age_group, sex)
);

CREATE TABLE funnel_defaults (
    id                  BIGSERIAL PRIMARY KEY,
    indication_id       INT NOT NULL REFERENCES indications(indication_id),
    country_code        CHAR(3) REFERENCES countries(country_code),  -- NULL = global
    stage               TEXT NOT NULL,      -- diagnosis_rate | treatment_rate | access_rate
    value               NUMERIC(6,4) NOT NULL,
    value_low           NUMERIC(6,4),
    value_high          NUMERIC(6,4),
    source              TEXT NOT NULL,
    confidence_tier     CHAR(1) NOT NULL,
    UNIQUE (indication_id, country_code, stage)
);

CREATE TABLE eligibility_criteria (
    criterion_id        SERIAL PRIMARY KEY,
    indication_id       INT NOT NULL REFERENCES indications(indication_id),
    criterion_code      TEXT NOT NULL,
    criterion_label     TEXT NOT NULL,
    criterion_type      TEXT NOT NULL,      -- bmi | comorbidity | hba1c | age
                                            -- line_of_therapy | prior_failure
    default_factor      NUMERIC(6,4) NOT NULL,
    factor_low          NUMERIC(6,4),
    factor_high         NUMERIC(6,4),
    source              TEXT NOT NULL,
    confidence_tier     CHAR(1) NOT NULL,
    correlated_with     TEXT[],             -- criterion codes that must not co-apply
    UNIQUE (indication_id, criterion_code)
);

CREATE TABLE drugs (
    drug_id             SERIAL PRIMARY KEY,
    drug_name           TEXT NOT NULL,
    generic_name        TEXT,
    company             TEXT,
    drug_class          TEXT,
    route               TEXT,
    indication_id       INT REFERENCES indications(indication_id),
    is_comparator       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE drug_regimens (
    regimen_id          SERIAL PRIMARY KEY,
    drug_id             INT NOT NULL REFERENCES drugs(drug_id),
    dose_amount         NUMERIC NOT NULL,
    dose_unit           TEXT NOT NULL,
    units_per_admin     NUMERIC NOT NULL,
    admins_per_year     NUMERIC NOT NULL,
    wastage_pct         NUMERIC(5,4) NOT NULL DEFAULT 0,
    persistence_12m     NUMERIC(5,4) NOT NULL DEFAULT 1.0,
    source              TEXT NOT NULL,
    confidence_tier     CHAR(1) NOT NULL
);

CREATE TABLE drug_prices (
    price_id            BIGSERIAL PRIMARY KEY,
    drug_id             INT NOT NULL REFERENCES drugs(drug_id),
    country_code        CHAR(3) NOT NULL REFERENCES countries(country_code),
    price_local         NUMERIC NOT NULL,
    currency_code       CHAR(3) NOT NULL,
    price_basis         TEXT NOT NULL,      -- list | nadac | estimated_net | ppp_derived
    annual_cost_usd     NUMERIC,
    gross_to_net_pct    NUMERIC(5,4),
    effective_date      DATE,
    source              TEXT NOT NULL,
    source_url          TEXT,
    confidence_tier     CHAR(1) NOT NULL
);

CREATE TABLE fx_rates (
    id                  BIGSERIAL PRIMARY KEY,
    currency_code       CHAR(3) NOT NULL,
    rate_per_usd        NUMERIC NOT NULL,
    fetched_date        DATE NOT NULL,
    UNIQUE (currency_code, fetched_date)
);
```

### 8.2 Scenario and Run Data

```sql
CREATE TABLE scenarios (
    scenario_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    description         TEXT,
    indication_id       INT NOT NULL REFERENCES indications(indication_id),
    asset_name          TEXT NOT NULL,
    asset_class         TEXT,
    development_stage   TEXT,
    launch_year         SMALLINT NOT NULL,
    horizon_years       SMALLINT NOT NULL DEFAULT 3
                        CHECK (horizon_years BETWEEN 1 AND 5),
    reporting_currency  CHAR(3) NOT NULL DEFAULT 'USD',
    country_codes       CHAR(3)[] NOT NULL,
    parent_scenario_id  UUID REFERENCES scenarios(scenario_id),
    is_baseline         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE scenario_overrides (
    id                  BIGSERIAL PRIMARY KEY,
    scenario_id         UUID NOT NULL REFERENCES scenarios(scenario_id)
                        ON DELETE CASCADE,
    country_code        CHAR(3),            -- NULL = applies to all markets
    parameter_path      TEXT NOT NULL,      -- e.g. funnel.diagnosis_rate
    value               JSONB NOT NULL,
    note                TEXT,
    UNIQUE (scenario_id, country_code, parameter_path)
);

CREATE TABLE model_runs (
    run_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id         UUID NOT NULL REFERENCES scenarios(scenario_id),
    engine_version      TEXT NOT NULL,
    run_type            TEXT NOT NULL,      -- forward | reverse | owsa | psa
    input_snapshot      JSONB NOT NULL,     -- fully resolved EngineInput
    fx_snapshot         JSONB NOT NULL,
    results             JSONB NOT NULL,
    duration_ms         INT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_model_runs_scenario ON model_runs (scenario_id, created_at DESC);
```

The `model_runs` table is append-only. Rows are never updated. `input_snapshot` contains every resolved value the engine consumed, so any run is reproducible by replaying it through the recorded `engine_version` — this is the mechanism that makes results auditable.

### 8.3 Knowledge Base

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE guideline_documents (
    document_id         SERIAL PRIMARY KEY,
    title               TEXT NOT NULL,
    issuing_body        TEXT NOT NULL,      -- ISPOR | NICE | WHO | CDA-AMC
    document_type       TEXT NOT NULL,
    publication_year    SMALLINT,
    source_url          TEXT,
    file_path           TEXT
);

CREATE TABLE guideline_chunks (
    chunk_id            BIGSERIAL PRIMARY KEY,
    document_id         INT NOT NULL REFERENCES guideline_documents(document_id),
    section             TEXT,
    page_number         INT,
    chunk_index         INT NOT NULL,
    chunk_text          TEXT NOT NULL,
    embedding           VECTOR(384) NOT NULL
);

CREATE INDEX idx_guideline_embedding
    ON guideline_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

---

## 9. Backend Architecture

### 9.1 Layer Model

Strict layering. Each layer depends only on the layer immediately below it, and dependencies point in one direction.

| Layer | Responsibility | May depend on | Must not |
|---|---|---|---|
| **Routes** | HTTP surface: path, method, status codes, OpenAPI annotation | Controllers, schemas | Contain business logic or touch the database |
| **Controllers** | Request/response orchestration, schema translation, HTTP error mapping | Services, schemas | Contain calculation logic or issue SQL |
| **Services** | Business logic, value resolution, transaction boundaries, engine invocation | Repositories, engine, schemas | Handle HTTP concerns or write raw SQL |
| **Repositories** | Query composition and aggregate-level persistence | DAL, models | Contain business rules |
| **DAL** | Session management, connection lifecycle, transaction primitives | SQLAlchemy models | Contain queries specific to a domain aggregate |
| **Engine** | Pure calculation | Nothing outside itself | Perform any I/O whatsoever |

### 9.2 Schema Layers

Three distinct Pydantic model families, deliberately not shared:

- **API schemas** (`schemas/`) — request and response contracts. Versioned with the API. Optimised for client ergonomics.
- **Engine models** (`engine/models.py`) — fully-resolved calculation inputs and outputs. No optional values, no defaults, no unresolved references. Every field is a concrete number with provenance attached.
- **ORM models** (`models/`) — SQLAlchemy declarative mappings. Persistence structure only.

Collapsing these into one family couples the HTTP contract to the database schema and to the calculation contract simultaneously. Keeping them separate means each can evolve independently, and the translation points are explicit and testable.

### 9.3 Engine Package Structure

```
biet_engine/
├── __init__.py           # __version__ — semantic, bumped on any behaviour change
├── models.py             # EngineInput, EngineResult, CountryResult, FunnelResult…
├── funnel.py             # M2, M3 — population derivation
├── uptake.py             # M4 — trajectories and substitution
├── persistence.py        # M6 — survival integral
├── cost.py               # M5 — cost of therapy, PPP derivation
├── impact.py             # M7 — incremental budget impact
├── affordability.py      # M8 forward — ratios and bands
├── solver.py             # M8 reverse — analytic and bisection price solving
├── sensitivity.py        # M9 — one-way deterministic
├── psa.py                # M9 — probabilistic simulation
└── distributions.py      # Beta/Gamma/Triangular parameterisation helpers
```

**Constraints enforced by test.** The engine package imports nothing from `fastapi`, `sqlalchemy`, `requests` or the application package. A dedicated test asserts this by inspecting the module dependency graph. Every function is pure: identical inputs produce identical outputs, with the sole exception of `psa.py`, which accepts an explicit random seed and is therefore deterministic given that seed.

**Versioning.** `biet_engine.__version__` follows semantic versioning. Any change altering a numerical result is at minimum a minor bump. The version is written into every run snapshot.

### 9.4 Engine Validation Strategy

Correctness is established by four independent test classes:

1. **Unit tests** — each function against hand-computed expected values.
2. **Golden cases** — complete worked scenarios with results derived independently and stored as fixtures. Any change to a golden result requires explicit review.
3. **Property-based tests** (hypothesis) — invariants that must hold across the input space. For example: budget impact is zero when uptake is zero; budget impact is monotonically non-decreasing in the new therapy's price; the persistence fraction lies in `(0, 1]` for all valid `p₁₂`; the funnel is monotonically non-increasing stage over stage.
4. **Reconciliation tests** — the reverse solver's output price, fed back through the forward calculation, must reproduce the target affordability ratio to within tolerance. This closes the loop between the two directions and is the strongest single check on the solver.

---

## 10. API Specification

Base path `/api/v1`. All responses are JSON. The OpenAPI 3.1 document is generated at `/openapi.json` and is the source from which frontend types are generated.

### 10.1 Reference Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/reference/countries` | Active markets with currency, archetype and economics |
| GET | `/reference/indications` | Available indications with default horizons |
| GET | `/reference/epidemiology` | Prevalence with bounds, filtered by indication and markets |
| GET | `/reference/drugs` | Comparator therapies with regimens and prices |
| GET | `/reference/criteria/{indication_id}` | Eligibility criteria library |
| GET | `/reference/fx` | Current foreign exchange snapshot |

### 10.2 Scenario Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/scenarios` | Create a scenario |
| GET | `/scenarios` | List scenarios |
| GET | `/scenarios/{id}` | Retrieve a scenario with resolved inputs |
| PATCH | `/scenarios/{id}` | Update scenario definition |
| POST | `/scenarios/{id}/clone` | Clone with optional override set |
| DELETE | `/scenarios/{id}` | Archive |
| PUT | `/scenarios/{id}/overrides` | Replace the override set |

### 10.3 Calculation Endpoints

| Method | Path | Description | Target latency |
|---|---|---|---|
| POST | `/scenarios/{id}/calculate` | Forward budget impact across all markets | < 200 ms |
| POST | `/scenarios/{id}/solve-price` | Reverse solve against an affordability target | < 300 ms |
| POST | `/scenarios/{id}/sensitivity` | One-way deterministic, tornado-ranked | < 1 s |
| POST | `/scenarios/{id}/psa` | Probabilistic simulation | < 5 s at 5,000 iterations |
| GET | `/scenarios/{id}/runs` | Run history |
| GET | `/runs/{run_id}` | Retrieve a stored run with its full snapshot |
| POST | `/scenarios/compare` | Multi-scenario comparison, 2–4 scenarios |

### 10.4 Evidence and Export Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/evidence/search` | Semantic retrieval over the guideline corpus |
| POST | `/scenarios/{id}/narrative` | Generate a cited executive narrative |
| POST | `/scenarios/{id}/export/pdf` | Full report with assumption register |
| POST | `/scenarios/{id}/export/pptx` | Executive deck |

### 10.5 Representative Response — Forward Calculation

```json
{
  "run_id": "…",
  "engine_version": "1.0.0",
  "reporting_currency": "USD",
  "fx_snapshot_date": "2026-08-18",
  "horizon_years": 3,
  "launch_year": 2028,
  "countries": [
    {
      "country_code": "DEU",
      "funnel": {
        "stages": [
          { "stage": "total_population",   "value": 83500000,
            "factor": null,   "source": "World Bank SP.POP.TOTL 2025", "tier": "A" },
          { "stage": "adult_population",   "value": 68470000,
            "factor": 0.820,  "source": "World Bank age structure",    "tier": "A" },
          { "stage": "diseased",           "value": 14132208,
            "factor": 0.2064, "source": "WHO NCD_BMI_30A 2024",        "tier": "A" },
          { "stage": "diagnosed",          "value": 8479325,
            "factor": 0.600,  "source": "Seeded default",              "tier": "C" },
          { "stage": "treated",            "value": 1271899,
            "factor": 0.150,  "source": "Seeded default",              "tier": "C" },
          { "stage": "label_eligible",     "value": 445165,
            "factor": 0.350,  "source": "Criterion stack",             "tier": "B" },
          { "stage": "addressable",        "value": 311615,
            "factor": 0.700,  "source": "Access assumption",           "tier": "C" }
        ]
      },
      "years": [
        {
          "year": 1, "calendar_year": 2028,
          "uptake": 0.05,
          "patients_on_new": 15581,
          "persistence_fraction": 0.721,
          "cost_without": 84213000,
          "cost_with":   142880000,
          "budget_impact": 58667000,
          "impact_per_patient": 3765,
          "affordability_ratio": 0.000103,
          "affordability_band": "low"
        }
      ],
      "cumulative_budget_impact": 331004000,
      "cumulative_affordability_ratio": 0.000579,
      "affordability_band": "low"
    }
  ],
  "totals": {
    "cumulative_budget_impact": 2847000000,
    "peak_year": 3,
    "peak_year_impact": 1420000000
  },
  "warnings": [
    {
      "code": "STALE_VINTAGE",
      "message": "Diabetes prevalence sourced from WHO NCD_GLUC_04 vintage 2014; projected forward to 2028."
    }
  ]
}
```

### 10.6 Representative Response — Reverse Solve

```json
{
  "run_id": "…",
  "target_affordability_ratio": 0.005,
  "method": "analytic",
  "price_corridor": [
    { "country_code": "USA", "max_annual_price_usd": 9840, "feasible": true },
    { "country_code": "DEU", "max_annual_price_usd": 4120, "feasible": true },
    { "country_code": "GBR", "max_annual_price_usd": 3610, "feasible": true },
    { "country_code": "JPN", "max_annual_price_usd": 2980, "feasible": true },
    { "country_code": "BRA", "max_annual_price_usd":  740, "feasible": true },
    { "country_code": "CHN", "max_annual_price_usd":  510, "feasible": true },
    { "country_code": "IND", "max_annual_price_usd":   96, "feasible": true }
  ],
  "binding_market": "IND",
  "single_global_price_ceiling_usd": 96
}
```

The `binding_market` and `single_global_price_ceiling_usd` fields make the central tension of global pricing explicit: a single worldwide price satisfying every market's affordability constraint is set by the poorest market, which is precisely why differential pricing exists.

---

## 11. Frontend Architecture

### 11.1 Slice Structure

```
frontend/src/
├── app/
│   ├── router.tsx              # Route definitions
│   ├── providers.tsx           # Query client, theme, error boundary
│   └── layout/                 # Shell, navigation, scenario switcher
├── features/
│   ├── scenario-builder/       # M1 — asset, markets, horizon, overrides
│   ├── population-funnel/      # M2, M3 — funnel visual, criterion stack
│   ├── market-uptake/          # M4 — uptake curve editor, substitution matrix
│   ├── cost-pricing/           # M5, M6 — regimen, price, persistence
│   ├── results-dashboard/      # M7 — impact by year and market, choropleth
│   ├── affordability/          # M8 forward — gauge, band classification
│   ├── price-solver/           # M8 reverse — corridor, binding market
│   ├── sensitivity/            # M9 — tornado, PSA distribution
│   ├── scenario-compare/       # M1 — side-by-side diff
│   └── evidence-copilot/       # M10 — retrieval, narrative, citations
└── shared/
    ├── api/                    # Generated client, query hooks
    ├── components/             # Design-system primitives
    ├── charts/                 # Chart wrappers with shared theming
    ├── hooks/
    ├── types/                  # Generated from OpenAPI
    └── utils/                  # Currency, number and date formatting
```

### 11.2 Boundary Rules

Enforced by `eslint-plugin-boundaries` at build time:

- A feature slice may import from `shared/` and from its own internals.
- A feature slice may **not** import from another feature slice's internals. Cross-slice communication occurs through route state, the scenario store, or `shared/`.
- `shared/` may not import from any feature slice.
- `app/` may import from anywhere; nothing may import from `app/`.

These rules give each slice a single public surface and make ownership boundaries explicit and mechanically checked, which is the property micro-frontends are usually adopted to obtain.

### 11.3 State Management

| State class | Mechanism | Rationale |
|---|---|---|
| Server state — reference data, calculation results, run history | TanStack Query | Caching, deduplication, stale-while-revalidate |
| Scenario draft — unsaved edits in the builder | Zustand store | Cross-slice access without prop drilling; simple, no boilerplate |
| Ephemeral UI — modals, accordions, tab selection | Component local state | No global coordination required |
| URL state — active scenario, active tab, selected markets | React Router search params | Deep-linkable and shareable |

### 11.4 Interactive Recalculation

Slider and numeric inputs drive recalculation through debounced calls to `POST /calculate` with a 250 ms trailing debounce, request cancellation on supersession, and optimistic retention of the previous result while the request is in flight.

Server-side calculation is retained as the single source of truth. Mirroring the engine in TypeScript would deliver lower latency at the cost of two implementations of the same arithmetic, which will diverge. The 200 ms latency budget on `/calculate` exists specifically to make the server round trip fast enough that a client-side mirror is unnecessary.

### 11.5 Principal Visualisations

| Visualisation | Feature | Library | Purpose |
|---|---|---|---|
| Patient funnel | population-funnel | Recharts (custom funnel) | Stage-by-stage narrowing with factor and provenance on hover |
| Impact by year | results-dashboard | Recharts stacked bar | World-without, incremental, world-with per year |
| Cross-market choropleth | results-dashboard | Plotly | Budget impact or affordability ratio by market |
| Affordability gauge | affordability | Recharts radial | Position against threshold bands |
| Price corridor | price-solver | Recharts horizontal bar | Maximum price by market, binding market highlighted |
| Tornado | sensitivity | Plotly | Inputs ranked by absolute swing |
| PSA distribution | sensitivity | Plotly histogram + CDF | Credible interval and threshold-exceedance probability |
| Scenario diff | scenario-compare | Recharts grouped bar | Side-by-side across all output dimensions |

---

## 12. AI and Retrieval Subsystem

### 12.1 Purpose and Boundary

The language model composes narrative and answers methodological questions. It does **not** produce numbers. Every quantitative value in generated text originates from the deterministic engine and is injected into the prompt as structured context. The model is instructed to reproduce supplied figures verbatim and is prohibited from computing, inferring or estimating any value.

This boundary is non-negotiable: the credibility of a budget impact estimate depends entirely on its arithmetic being traceable, and a generated number is by definition untraceable.

### 12.2 Corpus

| Document | Body | Role |
|---|---|---|
| Principles of Good Practice for Budget Impact Analysis (Task Force report) | ISPOR | Foundational methodology |
| Budget Impact Analysis — Principles of Good Practice II (2012 Task Force) | ISPOR | Updated methods and reporting guidance |
| Budget Impact Analysis editorial (2014) | ISPOR | Interpretation and commentary |
| Company budget impact analysis submission template | NICE | Submission structure and required fields |
| Budget impact test procedure | NICE | Affordability threshold mechanics |
| Budget impact analysis teaching materials | WHO | Methodological instruction |

### 12.3 Retrieval Pipeline

```
PDF/DOCX  →  text extraction  →  section-aware chunking (800 tokens, 100 overlap)
          →  embedding (BAAI/bge-small-en-v1.5, 384-dim)
          →  pgvector storage with document, section and page metadata
```

Query time: embed the query, retrieve the top `k` chunks by cosine similarity (default `k = 5`), filter below a similarity floor of 0.35, and return chunks with their document title, section and page number.

### 12.4 Narrative Generation

The prompt is assembled from three parts: the retrieved guideline passages, the structured engine results, and a system instruction constraining the model to the supplied material. Output is a structured executive narrative covering the population basis, the incremental impact and its drivers, the affordability position, the dominant uncertainties as identified by the tornado, and the stated limitations — with inline citations to the retrieved passages.

Every generated narrative is stored against its run identifier, so the text and the numbers it describes remain bound together.

### 12.5 Copilot

A conversational surface over the same retrieval index, scoped to methodological questions ("how should source of business be handled under ISPOR guidance?") and to interpretation of the current scenario's results. It has read access to the active run's structured results and to the guideline index, and no ability to modify a scenario.

---

## 13. Non-Functional Requirements

### 13.1 Performance

| Operation | Target | Method |
|---|---|---|
| Forward calculation, 10 markets, 5 years | < 200 ms | Vectorised NumPy; no I/O inside the engine |
| Reverse price solve, 10 markets | < 300 ms | Closed-form analytic path |
| One-way sensitivity, 20 parameters | < 1 s | Reuses the resolved input; 40 engine invocations |
| PSA, 5,000 iterations, 10 markets | < 5 s | Fully vectorised across iterations |
| Reference data query | < 50 ms | Indexed; cached in the service layer |
| Vector retrieval, top 5 | < 150 ms | ivfflat index, 100 lists |

### 13.2 Correctness and Auditability

- Every published value carries source, vintage year and confidence tier through to the interface and to exported deliverables.
- Every run is persisted with its complete resolved input, engine version and FX snapshot, and is exactly reproducible.
- The `model_runs` table is append-only.
- Any change to engine behaviour requires a version bump and updated golden fixtures.

### 13.3 Data Quality Controls

- Every ingested value is range-validated before publication; out-of-range values are quarantined in staging and do not supersede existing reference data.
- Values whose vintage exceeds a configured staleness threshold surface a `STALE_VINTAGE` warning on every run that consumes them.
- Projected values are flagged `is_projected` and are visually distinguished from observed values.
- Funnel monotonicity — each stage no larger than its predecessor — is asserted by the engine and raises a validation error rather than producing a silently wrong result.

### 13.4 Security

- No secret is present in source control. Configuration is environment-driven and validated at startup.
- Network proxy settings are optional environment variables; all ingestion operates identically with and without a proxy.
- The application database role holds no DDL privilege; migrations run under a separate role.
- API keys for the language model are read from the environment and are never logged or returned in responses.

### 13.5 Maintainability

- Backend type-checked with mypy in strict mode on the engine package.
- Frontend type-checked with TypeScript strict mode; API types are generated, never hand-written.
- Engine test coverage target: 95 percent statement coverage, 100 percent on `impact.py` and `solver.py`.
- Slice boundary rules enforced in CI.

---

## 14. Repository Layout

```
BIET/
├── docs/
│   └── ARCHITECTURE.md
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   │   └── versions/
│   ├── src/
│   │   ├── biet_engine/            # Pure calculation package (§9.3)
│   │   └── biet_api/
│   │       ├── main.py
│   │       ├── config.py           # pydantic-settings
│   │       ├── routes/
│   │       │   ├── reference.py
│   │       │   ├── scenarios.py
│   │       │   ├── calculations.py
│   │       │   ├── evidence.py
│   │       │   └── exports.py
│   │       ├── controllers/
│   │       ├── services/
│   │       │   ├── scenario_service.py
│   │       │   ├── resolution_service.py   # three-level value resolution
│   │       │   ├── calculation_service.py
│   │       │   ├── evidence_service.py
│   │       │   └── export_service.py
│   │       ├── repositories/
│   │       ├── dal/
│   │       │   ├── session.py
│   │       │   └── base.py
│   │       ├── models/             # SQLAlchemy ORM
│   │       └── schemas/            # API Pydantic contracts
│   └── tests/
│       ├── engine/
│       │   ├── unit/
│       │   ├── golden/
│       │   └── property/
│       └── api/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── .eslintrc.cjs               # boundary rules
│   └── src/                        # Slice structure (§11.1)
├── data/
│   ├── ingestion/
│   │   ├── sources/                # One module per source
│   │   ├── transform/
│   │   └── publish/
│   ├── seed/                       # Curated CSV reference seeds
│   └── corpus/                     # Guideline documents
├── docker-compose.yml
└── .env.example
```

---

## 15. Delivery Plan

Five phases. Phase boundaries are defined by demonstrable capability, not by elapsed time.

### Phase 1 — Data Foundation

- Ingestion scripts refactored: secrets removed, proxy made optional, retry and validation added.
- Source constraints of §7.2 implemented: WHO country and sex filtering, per-indicator latest-non-null-year resolution, adult-share derivation from World Bank age structure.
- Curated price seed table populated for branded incretins and comparators, each entry citing a public source with a stated gross-to-net assumption.
- NDC-to-regimen mapping established for insulin and generic comparators.
- Full schema created via Alembic; reference data published.

**Exit criterion.** Every reference table populated for all ten markets and both indications, with provenance and confidence tier on every row.

### Phase 2 — Calculation Engine

- `biet_engine` implemented in full: funnel, uptake, persistence, cost, incremental impact, affordability, solver, sensitivity, PSA.
- Golden fixtures established for both indications across a representative market set.
- Property-based invariants implemented.
- Reverse-solver reconciliation test passing.

**Exit criterion.** The engine executes standalone from a JSON input file and produces correct, reproducible results with no application layer present.

### Phase 3 — API and Core Interface

- Backend layers implemented; OpenAPI document stable.
- Frontend scaffolded with generated types and boundary rules enforced.
- Scenario builder, population funnel and results dashboard functional end to end.

**Exit criterion.** A user can define a scenario in the browser and obtain a correct multi-market budget impact result.

### Phase 4 — Analysis Capabilities

- Price solver with corridor visualisation.
- Affordability gauge and band classification.
- Tornado and PSA.
- Scenario comparison.

**Exit criterion.** All ten modules are functionally complete and reachable from the interface.

### Phase 5 — Evidence, Export and Hardening

- Guideline corpus ingested and indexed; retrieval operational.
- Narrative generation and copilot.
- PDF and PowerPoint export including the full assumption register.
- Performance targets verified; documentation completed.

**Exit criterion.** A complete scenario produces a distributable, fully cited deliverable.

---

## Appendix A — Glossary

| Term | Definition |
|---|---|
| **Addressable population** | Label-eligible patients with reimbursed access under the assumed formulary position |
| **Affordability ratio** | Budget impact expressed as a proportion of national current health expenditure |
| **Budget impact** | The difference in total cost between the world with and the world without the new therapy |
| **Confidence tier** | A–D grading of the evidential strength of a parameter value |
| **Diagnosis rate** | Proportion of the diseased population that has been clinically diagnosed |
| **Displacement** | Reduction in an incumbent therapy's share attributable to the new therapy |
| **Golden case** | A complete worked scenario with independently derived results, held as a regression fixture |
| **Gross-to-net** | The proportional reduction from list price to realised net price after rebates and discounts |
| **Launch-relative year** | Year index where Y1 is the launch year, independent of calendar year |
| **Line of therapy** | Position in the treatment sequence at which a therapy is used |
| **One-way sensitivity analysis (OWSA)** | Variation of one parameter at a time across its range, holding others at base case |
| **Persistence (12-month)** | Proportion of patients still receiving therapy twelve months after initiation |
| **Price corridor** | The set of market-specific maximum prices satisfying a common affordability target |
| **Probabilistic sensitivity analysis (PSA)** | Simultaneous Monte Carlo sampling of all uncertain parameters |
| **Provenance** | The source, vintage and confidence tier accompanying a parameter value |
| **Run snapshot** | Immutable record of a calculation's resolved inputs, engine version, FX rates and results |
| **Source of business** | The distribution of a new therapy's patients across their prior treatment states |
| **Treatment rate** | Proportion of diagnosed patients receiving pharmacological therapy |
| **Uptake** | Proportion of the addressable population receiving the new therapy in a given year |
| **Wastage** | Product dispensed but not administered, expressed as a proportional uplift on acquisition cost |
| **World with / world without** | The two comparison states whose cost difference defines budget impact |

---

## Appendix B — Default Parameter Values

All values below are seeded defaults, fully overridable at country and scenario level. Tier indicates evidential strength per §5.9.

### B.1 Demographic

| Parameter | Value | Tier | Note |
|---|---|---|---|
| Adult share — high-income markets (USA, GBR, DEU, FRA, ITA, ESP, JPN) | 0.78 – 0.86 | A | Derived as `1 - SP.POP.0014.TO.ZS / 100`; per-market values in §6.3 |
| Adult share — CHN, BRA | 0.78 – 0.82 | A | As above |
| Adult share — IND | 0.65 | A | As above |
| Population growth per annum | Per market, World Bank | A | Applied over the horizon |

### B.2 Funnel — Obesity

| Parameter | Default | Tier |
|---|---|---|
| Diagnosis rate | 0.60 | C |
| Treatment rate (pharmacological) | 0.15 | C |
| Access rate | 0.70 | C |

### B.3 Funnel — Type 2 Diabetes

| Parameter | Default | Tier |
|---|---|---|
| Diagnosis rate | 0.75 | C |
| Treatment rate (pharmacological) | 0.85 | C |
| Access rate | 0.80 | C |

### B.4 Uptake

| Parameter | Default | Tier |
|---|---|---|
| Curve family | Logistic | — |
| Year 1 uptake | 0.05 | C |
| Terminal uptake | 0.15 | C |
| Logistic steepness `k` | 1.2 | C |
| Inflection year `y_mid` | `N / 2` | — |

### B.5 Cost and Persistence

| Parameter | Default | Tier |
|---|---|---|
| Twelve-month persistence — incretin class | 0.50 | C |
| Twelve-month persistence — oral antidiabetic | 0.70 | C |
| Twelve-month persistence — insulin | 0.85 | C |
| Wastage — injectable pen | 0.05 | C |
| Wastage — oral | 0.02 | C |
| Gross-to-net — USA | 0.50 | C |
| Gross-to-net — EU markets | 0.20 | C |
| PPP income elasticity `ε` | 1.00 | C |
| PPP price floor | 0.05 | C |

### B.6 Analysis

| Parameter | Default |
|---|---|
| Time horizon | 3 years |
| Reporting currency | USD |
| PSA iterations | 5,000 |
| PSA random seed | 20260906 |
| OWSA variation where no range is published | ±20% |
| Solver tolerance | 1 × 10⁻⁶ relative |
| Solver maximum iterations | 100 |

---

## Appendix C — Reference Standards

| Standard | Body | Application in BIET |
|---|---|---|
| Principles of Good Practice for Budget Impact Analysis | ISPOR Task Force | Incremental world-with/world-without construction; decision-maker perspective; scenario-based presentation of uncertainty |
| Budget Impact Analysis — Principles of Good Practice II | ISPOR Task Force (2012) | Reporting structure; treatment-mix modelling; time-horizon convention |
| Company budget impact analysis submission | NICE | Assumption register content; required disclosure of data vintage and source |
| Budget impact test procedure | NICE | Affordability threshold mechanics informing the band classification in §5.7 |
| Budget impact analysis teaching materials | WHO | Epidemiological population derivation methodology |
| ISO 3166-1 alpha-3 | ISO | Country identification |
| ISO 4217 | ISO | Currency identification |
| Semantic Versioning 2.0.0 | — | Engine version discipline |

---

*End of document.*
