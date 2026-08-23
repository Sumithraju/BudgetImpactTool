# M9 — Uncertainty & Sensitivity

Module specification v1.0 · Owner area: Engine · Depends on: M7, M8

---

## 1. Purpose

Quantify the confidence interval around the estimate and rank assumptions by influence. At the
early stage BIET serves, the ranked list is more valuable than the point estimate: it tells the
team which evidence is worth buying before the decision is made.

## 2. Scope

**In scope.** One-way deterministic sensitivity and the tornado ranking; probabilistic sensitivity
analysis by Monte Carlo; distribution parameterisation from published intervals and confidence
tiers; threshold-exceedance probabilities.

**Out of scope.** Multi-way sensitivity. Expected value of perfect information. Scenario definition
(M1). Interpretation and narrative (M10).

## 3. Dependencies

Calls M7's forward calculation and, for price sensitivity, M8's solver. Produces `OwsaResult` and
`PsaResult`, consumed by M10.

## 4. Contracts

```python
class OwsaEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    parameter_path: str
    label: str
    base_value: float
    low_value: float
    high_value: float
    result_at_low: float            # cumulative BI, reporting currency
    result_at_high: float
    swing: float                    # abs(high - low)
    rank: int


class OwsaResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    base_result: float
    entries: tuple[OwsaEntry, ...]  # sorted by descending swing


class PsaResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    iterations: int
    seed: int
    mean: float
    median: float
    p2_5: float
    p97_5: float
    samples: tuple[float, ...]      # for the histogram/CDF; truncated to 5000
    exceedance: Mapping[str, float] # band name -> P(ratio > threshold)
    converged: bool


# biet_engine/sensitivity.py
def run_owsa(inputs: EngineInput, params: Sequence[SensitivityParam]) -> OwsaResult: ...

# biet_engine/psa.py
def run_psa(inputs: EngineInput, iterations: int, seed: int) -> PsaResult: ...
```

## 5. Logic specification

### 5.1 One-way deterministic sensitivity

For each parameter `x_i` with plausible range `[lo_i, hi_i]`, evaluate cumulative budget impact at
each bound with all other parameters at base case:

```
swing_i = | BI_total(x_i = hi_i) − BI_total(x_i = lo_i) |
```

Rank by descending swing. Cost: `2N + 1` forward evaluations for `N` parameters.

**Range selection**, in priority order:

1. Published bounds where they exist — WHO prevalence carries `low`/`high` directly.
2. Confidence-tier default relative standard error: A = as published, B = 15%, C = 30%, D = 50%,
   applied as `base × (1 ∓ 2 × rse)` to approximate a 95% range.
3. `OWSA_DEFAULT_VARIATION = 0.20` where neither applies.

Ranges are clipped to each parameter's valid domain — a rate cannot exceed 1, a price cannot go
below 0. Clipping is silent; it is a domain constraint, not a data problem.

**Parameters swept by default:** prevalence, adult share, diagnosis rate, treatment rate, access
rate, each enabled criterion factor, uptake terminal, new-therapy unit price, new-therapy
persistence, each comparator's persistence, wastage, discount, PPP elasticity, and the offset.

**Permissive mode.** OWSA runs M3's correlation guard in permissive mode (M3 §5.4) — a sweep that
transiently produces a correlated pair must warn, not abort the whole analysis.

### 5.2 Probabilistic sensitivity analysis

Sample all uncertain parameters simultaneously across `M` iterations (default 5,000, seed
`20260906`), and run the forward calculation on each draw.

| Parameter class | Distribution | Parameterisation |
|---|---|---|
| Prevalence | Beta | Method of moments from published mean and 95% bounds |
| Diagnosis, treatment, access rates | Beta | From mean and tier-derived SD |
| Criterion factors | Beta | From mean and tier-derived SD |
| Uptake terminal | Beta | From mean and tier-derived SD |
| Persistence `p₁₂` | Beta | From mean and tier-derived SD |
| Unit prices | Triangular | min, mode, max from the price scenario range |
| Admin, monitoring, AE costs | Gamma | Shape and scale from mean and SD |

**Standard deviation from a published interval:**

```
SD = (high − low) / CI_TO_SD_DIVISOR         # 3.92, the normal approximation to a 95% interval
```

Deriving prevalence distributions from WHO's own published bounds — rather than from assumed
variation — is what makes the uncertainty statement empirically grounded. Do not discard those
bounds anywhere in the pipeline.

**Beta by method of moments**, for mean `m` and variance `v`:

```
common = m(1 − m)/v − 1
alpha  = m × common
beta   = (1 − m) × common
```

Valid only when `v < m(1 − m)`. When the tier-derived SD violates this, shrink it to
`0.99 × sqrt(m(1−m))` and emit a `DISTRIBUTION_SHRUNK` warning rather than raising — an
over-wide assumed SD is a parameterisation artefact, not a modelling failure.

**Gamma:** `shape = m²/v`, `scale = v/m`.

**Triangular:** `min = mode × (1 − range)`, `max = mode × (1 + range)` unless explicit bounds are
supplied.

### 5.3 Vectorisation

PSA draws parameter arrays of shape `(M,)` and evaluates the forward calculation over the whole
sample at once, producing results of shape `(M, countries, years)`. At 5,000 × 10 × 5 this is
250,000 float64 values — trivially small.

**Do not implement PSA as a Python loop calling `compute_budget_impact` 5,000 times.** M7 §8
requires the inner computation to be array-based precisely so this module can broadcast over it.
A loop will miss the 5-second budget and will not scale if iterations rise.

### 5.4 Determinism

`numpy.random.default_rng(seed)` — never the legacy global `numpy.random` functions. The same seed
and the same inputs must produce identical samples on any machine. The seed is recorded in the run
snapshot; a PSA result that cannot be reproduced is not evidence.

### 5.5 Outputs

- `mean`, `median`, 2.5th and 97.5th percentiles of cumulative budget impact in the reporting
  currency.
- `exceedance[band]` = proportion of iterations whose cumulative affordability ratio exceeds each
  band threshold from M8.
- `converged`: true when the running mean over the final 10% of iterations is within 1% of the
  overall mean. False emits a `PSA_NOT_CONVERGED` warning suggesting more iterations.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| `iterations < 100` | Raise `ValueError` — too few for a meaningful interval |
| `iterations > 50_000` | Raise `ValueError` — exceeds the latency budget |
| Beta variance ≥ `m(1−m)` | Shrink SD, warn `DISTRIBUTION_SHRUNK` |
| `m = 0` or `m = 1` for a Beta parameter | Degenerate; hold at the point value, warn |
| Published `low = high` | Zero variance; hold at the point value |
| A sampled draw violating a domain constraint | Clip to the domain; count clips and warn if > 1% |
| Zero-swing OWSA parameter | Include with `rank` at the end; a parameter that does not move the answer is a finding |
| All swings zero | Valid — typically means uptake is zero |

## 7. Data requirements

Consumes `epidemiology.prevalence_low/high` and the `value_low`/`value_high` columns on
`funnel_defaults` and `eligibility_criteria`, plus `confidence_tier` everywhere. This is the
module that makes M0's insistence on populating bounds and tiers pay off.

## 8. API surface

| Method | Path | Latency target |
|---|---|---|
| POST | `/api/v1/scenarios/{id}/sensitivity` | < 1 s for 20 parameters |
| POST | `/api/v1/scenarios/{id}/psa` | < 5 s at 5,000 iterations |

PSA request accepts `iterations` and `seed`, both defaulted from constants. Both run types persist
to `model_runs` with `run_type` `owsa` / `psa`.

## 9. Frontend

Slice `features/sensitivity/`.

- `TornadoChart` — horizontal bars centred on the base case, sorted by swing, each labelled with
  the parameter and its low/high values (Plotly, via `shared/charts/`)
- `PsaHistogram` — distribution with the 95% credible interval marked
- `PsaCdf` — cumulative distribution with band thresholds overlaid
- `ExceedanceTable` — probability of exceeding each affordability band
- `SensitivityCallout` — names the top three drivers in plain language; this is the module's most
  actionable output and should not be buried below the charts

## 10. Test specification

| Class | Test |
|---|---|
| Unit | swing computed as absolute difference; ranking is descending |
| Unit | ranges from published bounds take priority over tier defaults |
| Unit | tier C with base 0.60 → range `[0.24, 0.96]` at 30% RSE |
| Unit | range clipped at 1.0 for a rate with base 0.90, tier C |
| Unit | Beta method of moments: `m=0.5`, `SD=0.1` → `alpha = beta = 12.0` |
| Unit | Beta with `v ≥ m(1−m)` shrinks SD and warns |
| Unit | Gamma: `m=100`, `SD=20` → `shape=25`, `scale=4` |
| Unit | `SD = (high − low)/3.92` for DEU obesity `[0.1759, 0.2391]` → 0.016122 |
| Unit | same seed produces identical samples across two invocations |
| Unit | `iterations = 50` raises |
| Unit | zero-swing parameter is retained in the ranking |
| Integration | PSA mean is within 2% of the deterministic base case for symmetric inputs |
| Integration | 5,000 iterations × 10 markets completes under 5 s |
| Property | PSA `p2_5 ≤ median ≤ p97_5` |
| Property | wider input intervals produce a wider output interval |

## 11. Acceptance criteria

- [ ] Pure; no I/O
- [ ] OWSA ranges use published bounds where available, tier defaults otherwise
- [ ] PSA prevalence distributions derived from WHO published bounds, not assumed variation
- [ ] PSA is vectorised, not looped
- [ ] `default_rng(seed)` only; results reproducible across machines
- [ ] Convergence checked and reported
- [ ] Latency targets met, asserted by benchmark
- [ ] 100% branch coverage on `sensitivity.py`, `psa.py`, `distributions.py`

## 12. Assumptions & open questions

**Assumptions.** Parameters are sampled independently — no correlation structure between, say,
prevalence and diagnosis rate. This is standard practice for budget impact PSA and is stated as a
limitation. Confidence-tier default widths (15/30/50%) are conventions, not empirical estimates,
and are exposed as constants so they can be re-based.

**Open question.** Whether correlated sampling is needed for the criterion stack, given M3 already
flags correlated criteria. If M3's correlation guard is used properly, independent sampling of the
combined factor is adequate; revisit only if tornado results look implausible.
