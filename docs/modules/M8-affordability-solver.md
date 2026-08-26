# M8 — Affordability & Price Solver

Module specification v1.0 · Owner area: Engine · Depends on: M5, M7

---

## 1. Purpose

Position budget impact against payer capacity, and invert that relationship to answer the question
that actually drives pre-launch decisions: **what price can this market afford?**

## 2. Scope

**In scope.** Affordability ratio against national health expenditure; band classification;
per-member-per-year for plan-level markets; the reverse price solver in both analytic and bisection
form; the cross-market price corridor and binding market.

**Out of scope.** Sensitivity around the solved price (M9). Narrative interpretation (M10).

## 3. Dependencies

Consumes `EngineResult` (M7) and `TherapyCost` structure (M5). Produces `AffordabilityResult` and
`PriceCorridor`, consumed by M9 and M10.

## 4. Contracts

```python
class AffordabilityBand(StrEnum):
    LOW = "low"; MODERATE = "moderate"; HIGH = "high"; CRITICAL = "critical"


class SolverMethod(StrEnum):
    ANALYTIC = "analytic"
    BISECTION = "bisection"


class CountryAffordability(BaseModel):
    model_config = ConfigDict(frozen=True)
    country_code: str
    health_budget: Money                    # local currency
    ratio_by_year: tuple[float, ...]
    cumulative_ratio: float
    band: AffordabilityBand
    pmpy: Money | None = None               # plan-level markets only


class CorridorEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    country_code: str
    max_unit_price_usd: float | None        # None when infeasible or unbounded
    max_annual_acquisition_usd: float | None
    feasible: bool
    unbounded: bool
    method: SolverMethod
    iterations: int | None = None


class PriceCorridor(BaseModel):
    model_config = ConfigDict(frozen=True)
    target_ratio: float
    entries: tuple[CorridorEntry, ...]
    binding_market: str | None
    single_global_price_ceiling_usd: float | None


# biet_engine/affordability.py
def compute_affordability(result: EngineResult, inputs: EngineInput) -> tuple[CountryAffordability, ...]: ...

# biet_engine/solver.py
def solve_price(inputs: EngineInput, target_ratio: float) -> PriceCorridor: ...
```

## 5. Logic specification

### 5.1 Forward affordability

```
HealthBudget(c,y)       = health_exp_pc(c) × Pop(c,y)
AffordabilityRatio(c,y) = BI(c,y) / HealthBudget(c,y)
cumulative_ratio(c)     = Σ(y) BI(c,y) / Σ(y) HealthBudget(c,y)
```

`Pop(c,y)` is the projected population from M2's first funnel stage — not the raw seeded value —
so the denominator grows consistently with the numerator.

Note the cumulative ratio is the ratio of sums, **not** the sum of ratios. The two differ whenever
the health budget varies across years.

**Bands.** Thresholds are constants (`AFFORDABILITY_THRESHOLDS`), applied to the cumulative ratio.

| Band | Cumulative ratio | Meaning |
|---|---|---|
| Low | < 0.10% | Unlikely to trigger budget-driven access restriction |
| Moderate | 0.10% – 0.50% | Managed entry or risk-sharing likely required |
| High | 0.50% – 1.00% | Significant reimbursement resistance expected |
| Critical | > 1.00% | Access improbable without price concession or volume cap |

A **negative** cumulative ratio — a budget saving — classifies as `LOW` and must be labelled as a
saving, not merely as low impact.

**PMPY.** For markets modelled at plan level, `pmpy = BI(c,y) / covered_lives(c)`. Only populated
where `covered_lives` is supplied; `None` otherwise (M0 §12 open question).

### 5.2 Reverse solver — framing

Reverse mode answers: *given an affordability ceiling `τ`, what is the maximum price?*

The solve variable `p` is the **unit price of the new therapy in the reference market, in USD**.
Because the asset is pre-launch, it has no observed price in any market; every market's price is
derived from `p` through the purchasing-power factor of M5 §5.3. The whole solve is performed in
USD, converting comparator costs and health budgets through the run's FX snapshot.

This refines the notation of ARCHITECTURE.md §5.8, which writes `p` as an annual acquisition price.
Solving on the **unit** price makes the regimen multipliers explicit in `α` and removes ambiguity
about whether wastage and discount are already folded in. Both forms are reported.

### 5.3 Linear decomposition

Using the reduced form of M7 §5.2, with `U = units_per_admin × admins_per_year`:

```
D(c,y)   = Addressable(c,y) × u(y)

ppp(c)   = max( [gdp_pc_ppp(c) / gdp_pc_ppp(ref)] ^ ε , floor )

α(c,y)   = D(c,y) × f_n × U × (1 + w_n) × (1 − d_n) × ppp(c)

β(c,y)   = D(c,y) × [ f_n × (admin_n + monitoring_n + ae_n − offset_n)
                      − Σ (t ∈ T) σ_t × f_t × AC(t,c) ]

BI(c,y)  = α(c,y) × p + β(c,y)
```

**The purchasing-power floor does not break linearity.** Since
`max(a·p, b·p) = p · max(a, b)` for `p > 0`, the floor is a constant multiplier on `p`, not a
piecewise function of it. ARCHITECTURE.md §5.8 lists the floor among the non-linear cases; that is
incorrect and the architecture document is being amended. What genuinely breaks linearity is a
discount that depends on price or volume.

### 5.4 Analytic solution

Applying the affordability constraint across the horizon:

```
Σ(y) [ α(c,y) × p + β(c,y) ] = τ × Σ(y) HealthBudget(c,y)

           τ × Σ(y) HealthBudget(c,y) − Σ(y) β(c,y)
p*(c)  =  ──────────────────────────────────────────
                      Σ(y) α(c,y)
```

Report both `p*` and the implied annual acquisition cost per patient:
`p* × U × (1 + w) × (1 − d)`.

### 5.5 Bisection fallback

Triggered when the configuration is non-linear in price — currently only tiered or
volume-dependent discounting — or when M4 reports a `SUBSTITUTION_FLOOR`, which invalidates the
reduced form the decomposition rests on.

- Bracket: `p ∈ [0, 10 × p_ref]`, where `p_ref` is the scenario's stated reference price.
- Objective: `g(p) = cumulative_ratio(p) − τ`, evaluated by running the full M7 forward calculation.
- Tolerance: `SOLVER_RELATIVE_TOLERANCE = 1e-6`. Cap: `SOLVER_MAX_ITERATIONS = 100`.
- If `g(0) > 0` the target is unreachable at any non-negative price → infeasible.
- If `g(10 × p_ref) < 0` the bracket is too narrow → widen once to `100 × p_ref`, then report
  unbounded.

The response records `method` and, for bisection, `iterations`.

### 5.6 Degenerate cases

| Condition | Result |
|---|---|
| `Σα = 0` — no patients reach the new therapy in any year | `unbounded = True`, `max_unit_price = None`, diagnostic warning. Any price satisfies the target because nobody receives the therapy. |
| `p* < 0` | `feasible = False`. The target cannot be met at any non-negative price: displaced-therapy savings are insufficient. Report the shortfall `Σβ − τ·ΣH`. |
| `Σα < 0` | Impossible by construction (all factors non-negative). Raise `SolverInvariantError`. |
| `τ ≤ 0` | Raise `ValueError` — an affordability target must be positive. |

### 5.7 Price corridor

Running the solver across all selected markets yields `{p*(c)}`.

```
binding_market                  = argmin over feasible c of p*(c)
single_global_price_ceiling_usd = min over feasible c of p*(c)
```

Markets that are infeasible or unbounded are excluded from the minimum but still reported, each
with its status. If **no** market is feasible, `binding_market` and the ceiling are `None`.

The corridor makes the central tension of global pricing explicit: a single worldwide price
satisfying every market's affordability constraint is set by the poorest market. Given health
expenditure per capita ranging from $13,473 (USA) to $85 (IND), the binding market will almost
always be India, and the resulting ceiling will be far below any commercially viable price. That is
the correct and useful finding — it is the quantified argument for differential pricing — and the
UI must present it as such rather than as an error.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| `τ ≤ 0` | Raise `ValueError` |
| `τ > 1` | Permitted but warn — a target above total health expenditure is meaningless |
| Missing `health_exp_pc` for a market | Raise `UnresolvedParameterError` |
| `health_exp_pc = 0` | Raise `ValueError` — division by zero |
| Negative cumulative ratio | Band `LOW`, labelled a saving |
| Reference market absent from the market set | Permitted — `ppp(ref)` is still computable |
| Bisection fails to converge in 100 iterations | Report `feasible = False` with a diagnostic; never return a partially converged value |
| All markets infeasible | `binding_market = None`, corridor still returned |

## 7. Data requirements

`country_economics.health_exp_pc_usd` and `population_total`, `fx_rates`, `gdp_pc_ppp`. Note
health expenditure resolves to 2023 or 2024 depending on market (M0 §5.2); the vintage is carried
and surfaced.

## 8. API surface

| Method | Path | Latency target |
|---|---|---|
| POST | `/api/v1/scenarios/{id}/calculate` | Affordability included in the forward response |
| POST | `/api/v1/scenarios/{id}/solve-price` | < 300 ms for 10 markets |

Request body: `{ "target_ratio": 0.005 }`. Response shape per ARCHITECTURE.md §10.6.

## 9. Frontend

Slices `features/affordability/` and `features/price-solver/`.

- `AffordabilityGauge` — radial gauge per market against the band thresholds; colour is paired with
  a text label, never colour alone
- `PriceCorridorChart` — horizontal bars of `p*(c)`, sorted ascending, binding market highlighted
  and annotated
- `BindingMarketCallout` — states the global ceiling and names the market that sets it, with a
  one-line explanation that differential pricing is the standard response
- Infeasible and unbounded markets render with explicit status chips, not blanks

## 10. Test specification

| Class | Test |
|---|---|
| Unit | ratio: `BI = 58,667,000`, budget `571.9e9` → 0.000103 |
| Unit | cumulative ratio is the ratio of sums, not the sum of ratios (constructed case where they differ) |
| Unit | band boundaries: 0.000999 → LOW, 0.001 → MODERATE, 0.005 → HIGH, 0.01 → CRITICAL |
| Unit | negative cumulative ratio → LOW, flagged as a saving |
| Unit | analytic `p*` for a single market with hand-computed α, β and H |
| Unit | PPP floor binding still yields the analytic path, not bisection |
| Unit | `Σα = 0` → unbounded with `max_unit_price = None` |
| Unit | `p* < 0` → infeasible with the shortfall reported |
| Unit | `τ = 0` raises; `τ = 1.5` warns |
| Unit | corridor picks the minimum feasible market as binding |
| Unit | all markets infeasible → `binding_market = None`, corridor still returned |
| Unit | bisection triggered when a tiered discount is present |
| Unit | bisection non-convergence reports infeasible, never a partial value |
| **Reconciliation** | `p*` fed back through M7 reproduces `τ` within 1e-6 — analytic path |
| **Reconciliation** | same, bisection path |
| Property | `p*` is monotonically increasing in `τ` |
| Property | `p*` is monotonically decreasing in uptake, all else equal |

The two reconciliation tests are the strongest single check in the system. They close the loop
between forward and reverse and will catch almost any error in either.

## 11. Acceptance criteria

- [ ] Pure; no I/O
- [ ] Analytic path used whenever the configuration is linear in price, including with an active
      PPP floor
- [ ] Bisection fallback implemented, bracketed, capped, and reporting its method and iterations
- [ ] All four degenerate cases handled per §5.6
- [ ] Corridor identifies the binding market and the global ceiling
- [ ] Both reconciliation tests pass on both paths
- [ ] `< 300 ms` for 10 markets, asserted by benchmark
- [ ] 100% branch coverage on `solver.py` and `affordability.py`

## 12. Assumptions & open questions

**Assumptions.** Reverse mode assumes no observed price in any market — appropriate for a
pre-launch asset. Uptake is independent of price; a lower price does not increase volume in this
model. Affordability is assessed against total national health expenditure, not a pharmaceutical
budget subset.

**Open questions.**
1. Whether the affordability denominator should be the **pharmaceutical** budget rather than total
   health expenditure. Pharmaceutical spend is roughly 10–20% of health expenditure, so the choice
   moves every ratio by nearly an order of magnitude and would require re-basing the band
   thresholds. Total health expenditure is used because it is the only figure available for all ten
   markets from a single consistent source. Flag prominently in M10's narrative.
2. Whether price-responsive uptake is wanted. It would make the solve genuinely non-linear and
   force bisection everywhere. Deferred.
