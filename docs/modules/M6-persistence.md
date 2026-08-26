# M6 — Persistence & Adherence

Module specification v1.0 · Owner area: Engine · Depends on: nothing

---

## 1. Purpose

Convert patient headcount into persistence-adjusted treatment-year equivalents. A patient who
discontinues at month five consumes five months of drug, not twelve.

This is the smallest module in the system and has no dependencies — a single closed-form function.
It is also, in cardiometabolic therapy, frequently the largest single correction applied to a naive
estimate. Build it first.

## 2. Scope

**In scope.** The exponential survival integral converting twelve-month persistence into a
treatment-year fraction; per-therapy application.

**Out of scope.** Time-to-discontinuation curve fitting. Prevalent-cohort carry-forward beyond the
stated simplification in §5.3. Adherence in the medication-possession-ratio sense — that is a
different concept and must not be conflated with persistence.

## 3. Dependencies

None. Consumes a scalar and returns a scalar. Consumed by M7 and M8.

## 4. Contracts

```python
# biet_engine/persistence.py
def persistence_fraction(p12: float) -> float:
    """Mean of the survival function over the first treatment year.

    Args:
        p12: proportion of patients still on therapy at 12 months, in (0, 1].

    Returns:
        Treatment-year fraction in (0, 1].

    Raises:
        ValueError: if p12 is not in (0, 1].
    """
```

## 5. Logic specification

### 5.1 Derivation

Assume exponential time-to-discontinuation with hazard `λ`, calibrated so `S(12) = p₁₂`:

```
λ = −ln(p₁₂) / 12
```

The treatment-year fraction is the mean of the survival function over the year:

```
f = (1/12) × INTEGRAL[m = 0 .. 12] e^(−λm) dm
  = (1 − e^(−12λ)) / (12λ)
```

Since `e^(−12λ) = p₁₂`, this reduces to a closed form with no integration at runtime:

```
f = (1 − p₁₂) / (−ln p₁₂)          for 0 < p₁₂ < 1
f = 1                              for p₁₂ = 1
```

### 5.2 Reference values

Assert all of these in tests.

| `p₁₂` | `f` | Interpretation |
|---|---|---|
| 1.00 | 1.0000 | Full-year persistence |
| 0.85 | 0.9230 | Insulin default |
| 0.70 | 0.8411 | Oral antidiabetic default |
| 0.50 | 0.7213 | Incretin class default |
| 0.30 | 0.5814 | — |
| 0.20 | 0.4971 | — |
| 0.05 | 0.3171 | — |

### 5.3 Application and its stated limitation

`f` is applied **per therapy**, not globally — the new therapy and its comparators differ
materially in discontinuation profile, and applying a single fraction across all of them erases
exactly the effect this module exists to capture.

**Stated simplification.** In steady state beyond year one, an incident cohort is supplemented by
the surviving prevalent cohort, so the true treatment-year fraction rises with year. For the 3–5
year horizons in scope, the first-year fraction is applied uniformly across all years. This is
**conservative** — it understates later-year drug consumption and therefore understates budget
impact. It is recorded as a model limitation in M10's narrative and in every export.

### 5.4 Numerical stability

- `p₁₂ = 1` is a removable singularity (`0/0`). Return 1.0 by explicit branch, not by limit
  evaluation.
- For `p₁₂` very close to 1, `−ln p₁₂` underflows toward 0. Use `math.log1p(p12 - 1)` for
  `p₁₂ > 0.999` to preserve precision.
- `p₁₂ = 0` is undefined — every patient discontinues instantly. Reject rather than returning 0.

## 6. Validation & edge cases

| Input | Behaviour |
|---|---|
| `p₁₂ = 1.0` | Return 1.0 exactly |
| `p₁₂ = 0.0` | Raise `ValueError` |
| `p₁₂ < 0` or `> 1` | Raise `ValueError` |
| `p₁₂` = NaN | Raise `ValueError` |
| `p₁₂ = 0.9999` | Use `log1p` path; result ≈ 0.99995 |

## 7. Data requirements

`drug_regimens.persistence_12m`, seeded per therapy class with tier C confidence and overridable
per scenario at `therapy.<drug_id>.persistence_12m`. Defaults per ARCHITECTURE.md Appendix B.5:
incretin 0.50, oral antidiabetic 0.70, insulin 0.85.

## 8. API surface

None. `persistence_fraction` appears in the calculation response as `years[].persistence_fraction`
per therapy.

## 9. Frontend

Within slice `features/cost-pricing/`. A `PersistenceInput` per therapy showing `p₁₂`, the derived
fraction `f`, and a short explanation of what the adjustment does. Because persistence typically
dominates the tornado (M9), the UI should make it prominent rather than burying it in an advanced
panel.

## 10. Test specification

| Class | Test |
|---|---|
| Unit | every row of the §5.2 table, to 4 decimal places |
| Unit | `p₁₂ = 1.0` returns exactly 1.0 |
| Unit | `p₁₂ = 0.0` raises `ValueError` |
| Unit | `p₁₂ = 1.5` raises `ValueError` |
| Unit | `p₁₂ = -0.1` raises `ValueError` |
| Unit | `p₁₂ = 0.9999` uses the `log1p` path and stays within 1e-9 of the analytic value |
| Property | `f ∈ (0, 1]` for all `p₁₂ ∈ (0, 1]` |
| Property | `f` is strictly increasing in `p₁₂` |
| Property | `f ≥ p₁₂` for all valid `p₁₂` (the mean of a decreasing survival function exceeds its endpoint) |
| Property | `f → 1` as `p₁₂ → 1` |

## 11. Acceptance criteria

- [ ] Closed form implemented; no runtime integration
- [ ] All seven reference values reproduce to 4 dp
- [ ] `p₁₂ = 1` handled by explicit branch
- [ ] `log1p` path for `p₁₂ > 0.999`
- [ ] `p₁₂ = 0` rejected
- [ ] All four property tests pass
- [ ] 100% branch coverage on `persistence.py`
- [ ] Docstring cites ARCHITECTURE.md §5.4

## 12. Assumptions & open questions

**Assumptions.** Exponential (constant-hazard) discontinuation. Real-world GLP-1 discontinuation is
front-loaded — hazard is higher in the first three months than later — so exponential is a
simplification that slightly *understates* early drop-off.

**Open question.** Whether a Weibull hazard with a shape parameter is worth the added input burden.
It would model front-loaded discontinuation more faithfully and requires one extra parameter. The
function signature would gain an optional `shape` argument, defaulting to 1.0 (exponential), so
this is a non-breaking extension. Decide only if sensitivity analysis shows the exponential
assumption materially moves the answer.
