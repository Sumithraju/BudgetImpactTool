# M3 — Eligibility & Segmentation

Module specification v1.0 · Owner area: Engine · Depends on: M0 (criterion library), M2

---

## 1. Purpose

Model the narrowing effect of label criteria and clinical positioning on the treated population,
as an ordered stack of independently toggleable, independently overridable factors. The difference
between a broad and a narrow label must be a visible, quantified step — never an opaque adjustment.

## 2. Scope

**In scope.** Criterion library; enable/disable per scenario; factor override; combination into a
single multiplier; correlation guarding; per-criterion provenance.

**Out of scope.** The funnel stages themselves (M2). Access and reimbursement (M2's `access_rate`).
Patient segmentation into cohorts with different costs — see §12.

## 3. Dependencies

Consumes the criterion library published by M0 and scenario overrides resolved by M1. Produces the
combined factor consumed by M2 at the `label_eligible` stage.

## 4. Contracts

```python
class CriterionType(StrEnum):
    BMI = "bmi"
    COMORBIDITY = "comorbidity"
    HBA1C = "hba1c"
    AGE = "age"
    LINE_OF_THERAPY = "line_of_therapy"
    PRIOR_FAILURE = "prior_failure"
    CONTRAINDICATION = "contraindication"


class Criterion(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str                       # "bmi_ge_30", "cv_comorbidity"
    label: str                      # "BMI >= 30 kg/m^2"
    type: CriterionType
    factor: Valued                  # in (0, 1]
    enabled: bool
    correlated_with: tuple[str, ...] = ()


class CriteriaResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    combined_factor: Valued
    applied: tuple[Criterion, ...]  # enabled only, in application order


# biet_engine/eligibility.py
def combine_criteria(criteria: Sequence[Criterion]) -> CriteriaResult: ...
```

## 5. Logic specification

### 5.1 Combination

Enabled criteria combine multiplicatively:

```
combined_factor = Π (k ∈ enabled) factor(k)
```

Disabled criteria contribute nothing — they are excluded, not set to 1.0, so that
`CriteriaResult.applied` is an accurate record of what was applied.

An empty enabled set yields `combined_factor = 1.0` with provenance
`source = "no criteria applied"`, tier C.

### 5.2 Interval propagation

Where criteria carry published bounds, propagate them as the product of bounds:

```
combined_low  = Π factor_low(k)
combined_high = Π factor_high(k)
```

If any enabled criterion lacks bounds, the combined result has `low = high = None` and M9 falls
back to the confidence-tier default width. Do not fabricate bounds.

### 5.3 Confidence tier of the combination

The combined tier is the **weakest** tier among applied criteria — a chain is no stronger than its
weakest link:

```python
combined_tier = max(c.factor.provenance.confidence_tier for c in applied)   # D > C > B > A
```

### 5.4 Correlation guarding

Criteria are assumed **conditionally independent**. This assumption fails where criteria overlap
clinically — BMI ≥ 35 and established cardiovascular disease are positively correlated, so
multiplying their marginal factors understates the joint population.

`correlated_with` lists codes that must not co-apply. Enabling two mutually-correlated criteria:

- raises `CorrelatedCriteriaError` in strict mode (default for API calls), **or**
- emits a `CORRELATED_CRITERIA` warning and proceeds in permissive mode (used by M9's sensitivity
  sweeps, where blocking would abort the analysis).

The remedy is a single combined criterion carrying an empirically derived joint factor, seeded in
`eligibility_criteria` by M0. Document the joint source on that row.

### 5.5 Seeded criterion library — obesity

Illustrative; authoritative values live in `data/seed/eligibility_criteria.csv` with citations.

| Code | Label | Type | Default factor | Tier |
|---|---|---|---|---|
| `bmi_ge_30` | BMI ≥ 30 kg/m² | `bmi` | 1.00 | A |
| `bmi_ge_35` | BMI ≥ 35 kg/m² | `bmi` | 0.55 | B |
| `bmi_27_with_comorb` | BMI ≥ 27 with ≥1 comorbidity | `bmi` | 1.15 → capped 1.00 | C |
| `cv_comorbidity` | Established cardiovascular disease | `comorbidity` | 0.35 | B |
| `age_18_75` | Age 18–75 | `age` | 0.88 | A |
| `no_prior_glp1` | No prior GLP-1 exposure | `prior_failure` | 0.70 | C |

`bmi_ge_35` and `cv_comorbidity` are declared correlated with each other.

**A factor may not exceed 1.0.** A criterion that *broadens* the population (BMI ≥ 27 with
comorbidity is a wider gate than BMI ≥ 30) must be modelled by replacing the base criterion, not
by a factor above 1 — otherwise funnel monotonicity breaks. Validation rejects factors > 1.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| `factor` in `(0, 1]` | Raise `ValueError` at construction |
| `factor > 1` | Rejected — see §5.5 |
| Two enabled criteria declaring each other in `correlated_with` | `CorrelatedCriteriaError` (strict) or warning (permissive) |
| Duplicate criterion codes | Raise `ValueError` |
| Criterion code not in the library for the indication | Raise `UnknownCriterionError` |
| All criteria disabled | `combined_factor = 1.0`, valid |
| Combined factor underflows below 1e-9 | Permitted; downstream population rounds to 0 |

## 7. Data requirements

`eligibility_criteria` (ARCHITECTURE.md §8.1). `correlated_with` is a `TEXT[]` of criterion codes.
Overrides address `criteria.<code>.factor` and `criteria.<code>.enabled`.

## 8. API surface

`GET /api/v1/reference/criteria/{indication_id}` returns the library. Selection and overrides flow
through M1's override set. No dedicated calculation endpoint.

## 9. Frontend

Within slice `features/population-funnel/`.

- `CriterionStack` — ordered list with a toggle, factor input, `<ProvenanceBadge>`, and the running
  cumulative factor after each row
- Correlated pairs are visually linked; enabling both shows an inline warning before submission
- The panel shows the resulting `label_eligible` population updating live via the debounced
  recalculation hook

## 10. Test specification

| Class | Test |
|---|---|
| Unit | three criteria 0.55 × 0.88 × 0.70 → 0.3388 |
| Unit | golden case: enabled stack products to 0.350 |
| Unit | disabled criteria are excluded from `applied`, not set to 1.0 |
| Unit | empty enabled set → 1.0 with a synthetic provenance |
| Unit | combined tier is the weakest among applied (A + C → C) |
| Unit | bounds propagate as the product of bounds |
| Unit | one criterion lacking bounds → combined bounds are `None` |
| Unit | factor of 1.15 raises `ValueError` |
| Unit | enabling `bmi_ge_35` and `cv_comorbidity` raises in strict mode |
| Unit | the same pair warns and proceeds in permissive mode |
| Property | combined factor ∈ `(0, 1]` for any valid enabled set |
| Property | combination is order-independent |

## 11. Acceptance criteria

- [ ] Pure; no I/O
- [ ] Golden case yields 0.350
- [ ] Factors > 1 rejected
- [ ] Correlation guard works in both strict and permissive modes
- [ ] Combined tier is the weakest applied tier
- [ ] Bounds propagate or degrade to `None` — never fabricated
- [ ] 100% branch coverage on `eligibility.py`

## 12. Assumptions & open questions

**Assumptions.** Conditional independence of enabled criteria, with correlated pairs handled by
substitution. Criteria apply uniformly across the treated population — no cohort splitting.

**Open question.** Whether patient *segmentation* — splitting the addressable population into
cohorts with different costs, uptake or persistence (for example BMI 30–35 versus ≥ 35) — is
needed for launch. It is out of scope for v1. Adding it later means `FunnelResult` returning a
tuple of segments rather than a scalar, which changes the M4 and M7 contracts. Confirm before
Phase 2 completes so the change is cheap if wanted.
