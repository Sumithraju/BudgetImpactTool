# M7 — Budget Impact Calculator

Module specification v1.0 · Owner area: Engine · Depends on: M2, M3, M4, M5, M6

---

## 1. Purpose

Execute the incremental world-with versus world-without comparison and aggregate the result across
therapies, markets and years. This is the definitional core of the system.

## 2. Scope

**In scope.** Cost of both worlds; incremental impact; per-patient impact; cumulative impact;
currency conversion to the reporting currency using the run's FX snapshot; cross-market
aggregation; peak-year identification.

**Out of scope.** Affordability positioning and the price solve (M8). Uncertainty (M9). Anything
that touches a database.

## 3. Dependencies

Consumes `FunnelResult` (M2), `MarketMix` (M4), `TherapyCost` (M5) and persistence fractions (M6).
Produces `EngineResult`, consumed by M8, M9 and M10.

## 4. Contracts

```python
class YearResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    year: int                       # launch-relative, 1-indexed
    calendar_year: int              # launch_year + year - 1, for display only
    uptake: float
    addressable: float
    patients_on_new: float
    cost_without: Money             # local currency
    cost_with: Money
    budget_impact: Money
    impact_per_patient: Money | None    # None when patients_on_new == 0


class CountryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    currency: str
    funnel: FunnelResult
    years: tuple[YearResult, ...]
    cumulative_budget_impact: Money


class EngineResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    engine_version: str
    reporting_currency: str
    fx_snapshot_date: date
    countries: tuple[CountryResult, ...]
    totals: Totals                  # reporting currency
    warnings: tuple[Warning_, ...]


# biet_engine/impact.py
def compute_budget_impact(inputs: EngineInput) -> EngineResult: ...
```

## 5. Logic specification

Per ARCHITECTURE.md §5.6.

### 5.1 The two worlds

For market `c`, year `y`, therapy set `T` (including `no_pharmacotherapy` and excluding the new
therapy `n`):

```
Cost_without(c,y) = Addressable(c,y) × Σ (t ∈ T) [ m_without(t,y) × f_t × AC(t,c) ]

Cost_with(c,y)    = Addressable(c,y) × [ u(y) × f_n × AC(n,c)
                                       + Σ (t ∈ T) m_with(t,y) × f_t × AC(t,c) ]

BI(c,y)           = Cost_with(c,y) − Cost_without(c,y)
```

`f_t` is the persistence fraction from M6, applied **per therapy**. `AC(t,c)` is the total annual
cost per full treated patient-year from M5.

### 5.2 Implement the full form, verify against the reduced form

ARCHITECTURE.md §5.6 gives a reduced form:

```
BI(c,y) = Addressable(c,y) × u(y) × [ f_n × AC(n,c) − Σ (t ∈ T) σ_t × f_t × AC(t,c) ]
```

**Implement the full two-world subtraction, not the reduced form.** The reduced form assumes
`m_with(t,y) = m_without(t,y) − u(y)·σ_t` exactly, which ceases to hold when M4's displacement
floor binds and the deficit is redistributed (M4 §5.4).

Use the reduced form as a **property test**: when no `SUBSTITUTION_FLOOR` warning was emitted, the
two forms must agree to within 1e-6 relative. This catches sign and indexing errors in the full
form, which is otherwise easy to get subtly wrong.

The bracketed term in the reduced form is the **net incremental cost per patient switched** — the
persistence-adjusted cost of the new therapy less the persistence-adjusted weighted cost of what it
displaces. Expose it in the response; it is the single most explanatory number in the model.

### 5.3 Negative budget impact is a valid result

Where the new therapy displaces a costlier incumbent, or where its offsets dominate, `BI` is
negative and the correct interpretation is a budget **saving**. Never floor at zero, never take an
absolute value, never rename it. A model that cannot report a saving is wrong.

### 5.4 Derived quantities

```
impact_per_patient(c,y) = BI(c,y) / (Addressable(c,y) × u(y))
cumulative(c)           = Σ (y = 1..N) BI(c,y)
```

`impact_per_patient` is `None` when `patients_on_new` is zero. Do not return 0 — zero impact per
patient and no patients are different statements, and rendering `0` would mislead.

### 5.5 Currency conversion

Per-market results stay in **local** currency. Aggregation converts to the reporting currency using
the run's FX snapshot, never a live lookup:

```
amount_reporting = (amount_local / rate_per_usd[local]) × rate_per_usd[reporting]
```

`fx_rates.rate_per_usd` is units of currency per one USD, with a USD identity row of 1.0. Convert
via USD as the pivot; do not chain conversions.

Rates come from `EngineInput.fx_rates`, which M1 snapshotted into the run. Re-executing a stored
run must reproduce results exactly — this is only true if the engine never reaches for a live rate.

### 5.6 Aggregation

```
Total(y)   = Σ (c) convert(BI(c,y))
Cumulative = Σ (y) Total(y)
peak_year  = argmax over y of Total(y)          # ties resolve to the earliest year
```

Aggregate the converted values, not the local ones. Summing across currencies without conversion
is a `CurrencyMismatchError`.

### 5.7 Rounding

Never round intermediate results. Round once, at serialisation, using the precision constants:
money to 2 decimal places, patient counts to integers, ratios to 6 significant figures.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| `u(y) = 0` for all y | `BI = 0` for all y; valid, no error |
| `patients_on_new = 0` | `impact_per_patient = None` |
| `BI < 0` | Valid — a saving |
| Missing FX rate for a market's currency | Raise `MissingFxRateError` |
| Missing FX rate for the reporting currency | Raise `MissingFxRateError` |
| Summing across currencies without conversion | Raise `CurrencyMismatchError` |
| New therapy present in the comparator set `T` | Raise `ValueError` — it must be excluded |
| Addressable = 0 | `BI = 0`, `impact_per_patient = None` |
| Horizon 1 | Valid; cumulative equals year 1 |

## 7. Data requirements

None directly — all inputs arrive resolved through `EngineInput`. Results are persisted by M1 into
`model_runs.results` as JSONB.

## 8. API surface

`POST /api/v1/scenarios/{id}/calculate` — target latency < 200 ms for 10 markets × 5 years
(ARCHITECTURE.md §13.1). The response shape is specified in §10.5 of the architecture document and
must match it exactly.

Performance approach: vectorise across years and therapies with NumPy. A Python loop over
`markets × years × therapies` at 10 × 5 × 8 is only 400 iterations and will meet the budget, but
M9's PSA calls this path 5,000 times — so the inner computation must be array-based from the start,
not retrofitted.

## 9. Frontend

Slice `features/results-dashboard/`.

- `ImpactByYearChart` — stacked bars: world-without, incremental, world-with per year
- `CountryImpactTable` — per-market cumulative impact, sortable
- `ChoroplethMap` — impact or affordability by market (Plotly, via `shared/charts/`)
- `NetCostPerSwitchCard` — the §5.2 bracketed term, prominently
- Negative impacts render as savings with distinct styling and an explicit "saving" label — never
  as a bare negative number in red, which reads as an error

All amounts through `formatMoney` with the currency from the response.

## 10. Test specification

### Golden case — Germany, obesity, Year 1

Inputs: addressable 311,615; uptake 0.05 → 15,580.75 patients (unrounded internally, displayed as
15,581); new therapy `f_n` 0.7213, `AC(n)` €4,800; single comparator with `m_without` 1.0, `σ` 1.0,
`f_t` 0.8411, `AC(t)` €1,200.

```
net cost per switch = 0.7213 × 4,800 − 1.0 × 0.8411 × 1,200 = 3,462.24 − 1,009.32 = 2,452.92
BI(DEU, 1)          = 311,615 × 0.05 × 2,452.92 = €38,218,333
```

Note the patient count is **not** rounded before multiplication (§5.7). Rounding to 15,581 first
gives €38,220,116 — a €1,783 discrepancy that compounds across markets and years. The test asserts
the unrounded figure.

| Class | Test |
|---|---|
| Unit | golden case reproduces to within €1 |
| Unit | zero uptake in every year yields zero impact |
| Unit | new therapy cheaper than the incumbent it displaces yields negative `BI` |
| Unit | `patients_on_new = 0` yields `impact_per_patient = None`, not 0 |
| Unit | new therapy included in `T` raises `ValueError` |
| Unit | missing FX rate raises `MissingFxRateError` |
| Unit | conversion DEU→USD at rate 0.86386 is exact and reversible |
| Unit | peak year with tied totals resolves to the earliest |
| Golden | full 10-market, 3-year run matches the stored fixture |
| Property | **full form equals reduced form** when no `SUBSTITUTION_FLOOR` warning |
| Property | `BI` is monotonically non-decreasing in the new therapy's unit price |
| Property | scaling addressable by k scales `BI` by k |
| Property | `cumulative = Σ years` for every market |

## 11. Acceptance criteria

- [ ] Pure; no I/O; no live FX lookup
- [ ] Full two-world form implemented; reduced form used only as a property test
- [ ] Negative impact reported as a saving, never floored
- [ ] `impact_per_patient` is `None`, not 0, when there are no patients
- [ ] Conversion pivots through USD using the run's snapshot
- [ ] No intermediate rounding
- [ ] Array-based inner computation, ready for M9's 5,000 iterations
- [ ] `< 200 ms` for 10 markets × 5 years, asserted by a benchmark test
- [ ] 100% branch coverage on `impact.py`

## 12. Assumptions & open questions

**Assumptions.** Costs are constant across the horizon (M5 §12). One uptake trajectory applies to
all markets unless overridden per market. Discounting of future costs is **not** applied — budget
impact analysis reports undiscounted cash flows by ISPOR convention, unlike cost-effectiveness
analysis.

**Open question.** Whether an optional discount rate should be offered for markets whose HTA body
requires it. Deferred; adding it is a per-year multiplier and does not change the contract.
