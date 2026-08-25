# M15 — Evidence-Gap Intelligence

Module specification v1.0 · Owner area: Backend · Depends on: M9, M10

---

## 1. Purpose

Rank the parameters worth acquiring evidence for, by combining how much each moves the answer with
how weak its current basis is.

M9 already computes how much each input moves cumulative budget impact. Every resolved value already
carries a confidence tier. Neither alone answers the question an analyst actually has after reading
a tornado diagram, which is not "what is uncertain" but "what should I go and find out". A parameter
with a large swing and a published country-specific source is settled. A parameter with a large
swing and a placeholder is the reason the answer cannot yet be trusted. Only the product separates
them.

## 2. Scope

**In scope.** Joining sensitivity swing to confidence tier per parameter; the priority score and its
bands; the ranked output in the API, the interface and the export.

**Out of scope.** Deciding tiers (M0 and the resolution chain). Computing swings (M9). Suggesting
where evidence might be found — the module says what is worth knowing, not where to look.

## 3. Dependencies

**Upstream.** M9's one-way sensitivity result; the provenance attached to every resolved value.

**Downstream.** M10's narrative and export, which report the ranking alongside the limitations.

## 4. Contracts

```python
class EvidencePriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    SUFFICIENT = "sufficient"


class EvidenceGap(BaseModel):
    model_config = ConfigDict(frozen=True)

    parameter_path: str              # "therapies.3.unit_price"
    label: str
    swing: Money                     # from M9, reporting currency
    influence: float                 # swing / max swing, [0, 1]
    confidence_tier: ConfidenceTier
    weakness: float                  # W(tier)
    priority_score: float            # influence × weakness
    priority: EvidencePriority
    source: str                      # what the value currently rests on
    country_code: str | None


class EvidenceGapReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    gaps: tuple[EvidenceGap, ...]    # ranked, highest priority first
    max_swing: Money
```

```python
# biet_engine/evidence_gap.py — pure
def rank_evidence_gaps(
    swings: Sequence[SensitivityEntry], provenance: Mapping[str, Provenance],
) -> EvidenceGapReport: ...
```

## 5. Logic specification

### 5.1 Weakness weights

```
A → 0.05    published, country-specific, with a stated interval
B → 0.25    published, regional or extrapolated
C → 0.60    analogue-derived or expert assumption
D → 1.00    placeholder requiring replacement
```

Tier A is 0.05 rather than 0 deliberately: a published country-specific figure can still be the
thing most worth re-checking if it dominates the tornado, and a weight of zero would make that
impossible to see. The gap between C and D is the widest because it is the one that matters — an
analogue-derived assumption is an analysis, a placeholder is an admission.

### 5.2 Priority

```
influence_i = swing_i / max(j) swing_j
priority_i  = influence_i × weakness_i
```

Bands: `critical ≥ 0.50`, `high ≥ 0.25`, `medium ≥ 0.10`, otherwise `sufficient`.

Normalising by the maximum swing rather than by total budget impact makes the ranking scale-free and
comparable across scenarios and markets, at the cost of making the top parameter's influence always
exactly 1.0. That is acceptable because the output is a ranking, not a magnitude.

A parameter with zero swing scores zero however weak its source. This is the point of the module,
not a limitation of it: time spent pinning down a value that cannot move the result is time not
spent on the one that can.

### 5.3 What it does not do

The ranking is a function of this scenario. A parameter that is `sufficient` here can be `critical`
in another market or at another price point, and the report says so rather than implying a general
truth about the parameter.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| All swings zero | Every influence 0, every priority `sufficient`, no division by zero |
| A parameter with no provenance | Treated as tier D and flagged — an unattributed value is a placeholder by definition |
| Ties in priority score | Broken by descending swing, then by parameter path, so ordering is stable |
| Single parameter | Influence 1.0; band determined by tier alone |

## 7. Data requirements

None. Computed from a sensitivity result and the provenance already carried by resolved values.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/scenarios/{id}/evidence-gaps` | Ranked; runs a one-way sensitivity if none is cached |

## 9. Frontend

Slice `features/results/`, beside the tornado it reinterprets.

- `EvidencePriorityPanel` — ranked list with band, swing, tier and current source
- Each row states what the value currently rests on, because that is what a reader needs in order
  to judge whether it is worth improving

## 10. Test specification

| Class | Test |
|---|---|
| Unit | weights and bands match §5.1 and §5.2 exactly |
| Unit | high swing + tier D outranks high swing + tier A |
| Unit | zero swing + tier D scores zero |
| Unit | all-zero swings produce no division by zero |
| Unit | missing provenance is treated as tier D and flagged |
| Unit | ties break deterministically |
| Integration | the ranking's top entry differs from the tornado's top entry when tiers differ |

## 11. Acceptance criteria

- [ ] Priority is influence × weakness, with the weights and bands as specified
- [ ] A high-swing tier-D parameter outranks a high-swing tier-A one
- [ ] A zero-swing parameter is never a priority
- [ ] Every row states the source the value currently rests on
- [ ] The ranking appears in the exported deliverable, not only in the interface

## 12. Assumptions & open questions

**Assumptions.** Tier is an adequate proxy for evidence weakness. It is coarse — two tier-B values
can differ substantially in how well founded they are — but it is the only such signal the system
carries on every value, and a finer one would have to be invented rather than observed.

**Open questions.**
1. Whether to incorporate the width of a published interval where one exists, which would separate
   two tier-A values of different precision.
2. Whether influence should be computed from a probabilistic analysis rather than a one-way
   deterministic one. It would capture interaction effects the tornado misses, at the cost of a
   ranking that changes slightly between runs.
