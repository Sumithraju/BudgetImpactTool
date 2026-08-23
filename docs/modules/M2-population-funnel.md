# M2 — Population Funnel Engine

Module specification v1.0 · Owner area: Engine · Depends on: M0 (data), M1 (resolution)

---

## 1. Purpose

Derive the addressable patient population for each market and each launch-relative year through an
ordered, auditable sequence of stages. The funnel is the canonical structure of the system; its
intermediate stages are what make the estimate defensible.

## 2. Scope

**In scope.** Population projection; adult-share adjustment; prevalence application; diagnosis,
treatment and access rates; stage-by-stage output with per-stage provenance; monotonicity
enforcement.

**Out of scope.** Eligibility criteria (M3 — this module consumes their combined factor). Uptake
(M4). Any I/O.

## 3. Dependencies

Consumes `CountryInput` from M1. Consumes the combined criterion factor from M3. Produces
`FunnelResult` consumed by M4 and M7.

## 4. Contracts

```python
# biet_engine/models.py
class FunnelRates(BaseModel):
    model_config = ConfigDict(frozen=True)
    diagnosis_rate: Valued
    treatment_rate: Valued
    access_rate: Valued


class FunnelStageResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    stage: FunnelStage
    value: float
    factor: float | None            # None for the first stage
    provenance: Provenance | None


class FunnelResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    country_code: str
    year: int                       # launch-relative, 1-indexed
    stages: tuple[FunnelStageResult, ...]

    @property
    def addressable(self) -> float:
        return self.stages[-1].value


# biet_engine/funnel.py
def compute_funnel(
    country: CountryInput,
    criteria_factor: Valued,        # from M3
    year: int,
) -> FunnelResult: ...
```

Pure. No I/O. Deterministic.

## 5. Logic specification

Per ARCHITECTURE.md §5.2:

```
Pop(c,y)         = population_total(c) × (1 + pop_growth(c))^(y-1)
Adult(c,y)       = Pop(c,y) × adult_share(c)
Diseased(c,y)    = Adult(c,y) × prevalence(c, indication)
Diagnosed(c,y)   = Diseased(c,y) × diagnosis_rate(c)
Treated(c,y)     = Diagnosed(c,y) × treatment_rate(c)
Eligible(c,y)    = Treated(c,y) × criteria_factor        ← from M3
Addressable(c,y) = Eligible(c,y) × access_rate(c)
```

`y` is launch-relative and 1-indexed; `y = 1` applies growth exponent 0.

### 5.1 The denominator alignment constraint

This is the single most important rule in the module and the easiest to get silently wrong.

WHO indicators `NCD_BMI_30A` and `NCD_GLUC_04` publish prevalence for **adults aged 18 and over**.
World Bank `SP.POP.TOTL` reports **total population, all ages**. Applying an adult prevalence rate
to a total-population denominator inflates the diseased population by the paediatric share —
approximately 22% in high-income markets and approximately 35% in India.

`adult_share` is therefore a **mandatory** stage. It is not optional and must not be defaulted to
1.0 under any circumstance. If `adult_share` is unresolvable for a market, raise
`UnresolvedParameterError` rather than proceeding.

### 5.2 Access rate versus uptake

`access_rate` is the proportion of label-eligible patients with reimbursed access under the assumed
formulary position — who *may* receive the therapy. Uptake (M4) is what proportion of those
actually do. Conflating them double-counts or under-counts. `access_rate` belongs here; uptake
does not.

### 5.3 Provenance propagation

Each stage records the factor that produced it and that factor's provenance. The first stage
(`total_population`) has `factor = None` and carries the population figure's own provenance.
Dropping provenance anywhere in the chain is a defect.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| **Monotonicity** — each stage ≤ its predecessor | Raise `FunnelInvariantError` |
| All factors in `(0, 1]` | Raise `ValueError` at construction |
| `adult_share` missing | Raise `UnresolvedParameterError` — never default |
| `prevalence` in `(0, 1)` exclusive | Raise `ValueError` |
| `population_growth` may be negative (JPN, ITA) | Permitted; range `(-0.05, 0.05)` |
| Any stage resolves to 0 | Permitted; downstream impact is 0, no error |
| `year < 1` | Raise `ValueError` |

Monotonicity can only fail if a factor exceeds 1, so the invariant is a cheap guard against a
data-entry or unit error (a rate entered as `60` instead of `0.60`). Raise rather than clamp — a
clamped funnel produces a plausible wrong number, which is the failure mode this system must not
have.

## 7. Data requirements

Consumes resolved values only. Originating tables, for reference: `countries.adult_share`,
`country_economics` (`population_total`), `epidemiology.prevalence_pct`, `funnel_defaults`
(`diagnosis_rate`, `treatment_rate`, `access_rate`).

Note `epidemiology.prevalence_pct` is stored as a percentage; M1's repository converts it to a
fraction at the boundary. The engine only ever sees fractions.

## 8. API surface

None directly. Surfaces through `POST /scenarios/{id}/calculate` as the `funnel.stages` array
(ARCHITECTURE.md §10.5).

## 9. Frontend

Slice `features/population-funnel/`.

- `FunnelChart` — stage-by-stage narrowing; each stage shows absolute value, the factor applied,
  and `<ProvenanceBadge>` on hover
- `FunnelTable` — the same data as an accessible table (charts must have a text alternative)
- Stage values use `formatCount`; factors use `formatPercent` (which takes a fraction)

## 10. Test specification

### Golden case — Germany, obesity, Year 1

| Stage | Factor | Expected |
|---|---|---|
| `total_population` | — | 83,500,000 |
| `adult_population` | 0.820 | 68,470,000 |
| `diseased` | 0.2064 | 14,132,208 |
| `diagnosed` | 0.600 | 8,479,325 |
| `treated` | 0.150 | 1,271,899 |
| `label_eligible` | 0.350 | 445,165 |
| `addressable` | 0.700 | 311,615 |

Tolerance: 1 unit (rounding at the final stage only).

| Class | Test |
|---|---|
| Unit | golden case above reproduces exactly |
| Unit | year 2 applies growth exponent 1, year 1 exponent 0 |
| Unit | negative population growth reduces the population (JPN) |
| Unit | omitting `adult_share` raises, does not default to 1.0 |
| Unit | a factor of 1.2 raises `FunnelInvariantError` |
| Unit | prevalence of 20.64 (percent, not fraction) raises `ValueError` |
| Unit | every stage carries provenance; none is `None` except stage 0's factor |
| Property | funnel is monotonically non-increasing for all valid inputs |
| Property | `addressable ≤ total_population` always |
| Property | scaling `total_population` by k scales every stage by k |

## 11. Acceptance criteria

- [ ] `compute_funnel` is pure — no imports outside `biet_engine`
- [ ] Golden case reproduces to within 1 unit
- [ ] Monotonicity enforced by exception, never by clamping
- [ ] `adult_share` mandatory; absence raises
- [ ] Provenance present on every stage
- [ ] Property tests pass
- [ ] `mypy --strict` clean; 100% branch coverage on `funnel.py`

## 12. Assumptions & open questions

**Assumptions.** Prevalence is constant across the horizon unless a projected series is supplied —
population growth is the only time variation applied. Incidence-based funnels are out of scope;
this is a prevalence-based model.

**Open question.** Whether population growth should use a per-market World Bank series rather than
a single scalar. A scalar is sufficient for a 3–5 year horizon; the contract accepts a `Valued` so
switching to a series is a non-breaking change to `CountryInput`.
