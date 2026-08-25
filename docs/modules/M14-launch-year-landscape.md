# M14 — Launch-Year Competitive Landscape

Module specification v1.0 · Owner area: Engine + Backend · Depends on: M4, M11, M12

---

## 1. Purpose

Project the market a not-yet-launched asset will actually meet, by admitting discovered pipeline
entrants into the baseline mix from their expected entry year.

An asset launching in four years does not compete against today's market. A Phase III competitor
approved two years from now is part of the world-without from year three onward, and a budget impact
computed against the current mix silently assumes it away. That assumption may be the right one —
it is conservative and it is defensible — but it should be a choice rather than an oversight.

## 2. Scope

**In scope.** Pipeline entrant retrieval with sponsor, phase, status and primary completion date;
expected entry year derivation; entrant share ramp; proportional rescaling of incumbent shares; the
side-by-side reporting of current-market and launch-year results.

**Out of scope.** Predicting whether a trial succeeds, whether an asset is approved, or at what
price. Forecasting uptake for anything other than the modelled asset. Any automatic admission of an
entrant into a base case (§5.5).

## 3. Dependencies

**Upstream.** M11's pipeline bucket; M12's `expected_entry_year` and `assumed_terminal_pct`;
ClinicalTrials.gov, already ingested by M0.

**Downstream.** M4's baseline shares, which M7 consumes as `m_without(t, y)`.

## 4. Contracts

```python
class PipelineEntrant(BaseModel):
    model_config = ConfigDict(frozen=True)

    drug_id: int                      # promoted; an entrant needs a price like any therapy
    name: str
    sponsor: str | None
    max_clinical_stage: ClinicalStage
    primary_completion: date | None
    entry_year: int                   # launch-relative, >= 1
    terminal_share: Valued            # plateau share of the addressable market
    ramp_years: int                   # years from entry to plateau


class LandscapeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    baseline_shares: Mapping[int, tuple[float, ...]]   # drug_id -> per-year, entrants included
    admitted: tuple[PipelineEntrant, ...]
    warnings: tuple[Warning_, ...]
```

```python
# biet_engine/landscape.py — pure
def expected_entry_year(
    primary_completion: date, *, launch_year: int, regulatory_lag_years: float,
) -> int: ...

def project_landscape(
    baseline: Mapping[int, tuple[float, ...]],
    entrants: Sequence[PipelineEntrant],
    *, horizon_years: int,
) -> LandscapeResult: ...
```

## 5. Logic specification

### 5.1 Expected entry year

```
y_e = max( 1, ⌈ completion_year + regulatory_lag - L + 1 ⌉ )
```

launch-relative, with `regulatory_lag` defaulting to 1.5 years — approximately the interval from
primary completion to approval for a priority-review asset with a clean readout, and optimistic for
anything else. It is a named constant and a sensitivity lever, not a literal.

An entrant whose expected entry falls beyond the horizon is reported and not modelled: it cannot
affect a result that ends before it arrives, and including it as a zero row would suggest otherwise.
An entrant with no primary completion date cannot have an entry year derived and must have one
entered directly.

### 5.2 Entrant share trajectory

```
m_e(y) = 0                                          for y < y_e
m_e(y) = s_e × min( 1, (y - y_e + 1) / r_e )        for y ≥ y_e
```

A linear ramp to plateau, matching M4's linear uptake curve. Logistic diffusion would be equally
defensible and is not more accurate given that `s_e` is itself an assumption — a second shape
parameter on top of a guessed plateau adds precision without adding information.

### 5.3 Incumbent rescaling

Entrants take share proportionally from every incumbent, not from a nominated one:

```
E(y) = Σ(e) m_e(y),        capped at MAX_ENTRANT_TOTAL_SHARE

m'_t(y) = m_t(y) × ( 1 - E(y) )
```

so `Σ(t) m'_t(y) + Σ(e) m_e(y) = 1` at every year, which is the invariant M4 already requires of a
baseline mix and which a property test asserts here.

Proportional rescaling is used because no public source says which incumbent an entrant displaces.
Nominating one would be a market-access judgement dressed as a computation. A user who has that
judgement can express it directly through the substitution vector, where it belongs and where it is
visible as an assumption.

The cap exists because an unbounded entrant total can drive incumbent shares to zero and leave the
world-without consisting entirely of drugs that do not yet exist, which is not a market and not a
comparison.

### 5.4 What this changes, and why it can go either way

Admitting an entrant changes `Cost_without`, and therefore budget impact, in both directions:

- A **cheaper** entrant lowers the world-without cost, so the new asset's incremental impact **rises**.
- A **more expensive** entrant raises it, so incremental impact **falls** — the new asset now
  displaces something dearer than what is on the market today.

Neither direction is the "right" answer and the module takes no view. What it does is make the
mechanism visible: the result is reported beside the current-market base case, with the delta
attributable to entrant admission stated explicitly.

### 5.5 A scenario, never a base case

Every entrant carries three assumptions the evidence does not supply: that it is approved, when, and
at what price. All three are tier D by construction. Therefore:

- Landscape projection is **off** unless explicitly enabled.
- Enabling it emits `PIPELINE_ENTRANT_MODELLED`, naming every entrant admitted, its entry year and
  its assumed plateau share.
- Its result is reported **beside** the current-market base case, never in place of it.
- An entrant must be promoted (M12) before it can be modelled — it needs a price like any other
  therapy, and the price will be an assumption, which is exactly why it must be entered rather than
  invented.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| `entry_year > horizon_years` | Reported, not modelled |
| `entry_year < 1` | Clamped to 1 — an entrant already marketed at launch is an incumbent |
| No primary completion date | Entry year must be supplied directly |
| Entrant total exceeds the cap | Scaled to the cap, `ENTRANT_SHARE_CAPPED` warning |
| Entrant not promoted | `ComparatorNotPricedError` (M12 §5.6) |
| Zero entrants admitted | Baseline returned unchanged, no warning — the ordinary case |
| Shares fail to sum to 1.0 after rescaling | `DisplacementError`; never returned |
| Entrant is the modelled asset itself | Rejected — it is on the world-with side by definition |

## 7. Data requirements

Reads `comparator_assets` for pipeline records and their derived entry years. Adds no tables of its
own; `expected_entry_year` and `assumed_terminal_pct` live on `comparator_assets` (§8.4) because
they are properties of the asset rather than of a run.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/comparators/landscape` | `?indication_id=1&launch_year=2030&horizon_years=3` |

The forward calculation accepts a flag to project the landscape; its response then carries both
baselines and the warning naming what was admitted.

## 9. Frontend

Slice `features/comparator-discovery/`.

- `LandscapeTimeline` — entrants on a launch-relative axis, with sponsor, phase and completion date
- `MarketAtLaunch` — current mix and projected mix side by side, per year
- Projection is a toggle, off by default, with the tier-D caveat stated at the toggle rather than
  in a footnote

## 10. Test specification

| Class | Test |
|---|---|
| Unit | entry year from a completion date plus lag, hand-computed |
| Unit | completion already past clamps to year 1 |
| Unit | entrant beyond the horizon is reported and not modelled |
| Unit | ramp reaches plateau exactly at `entry_year + ramp_years - 1` |
| Unit | share before entry year is exactly zero |
| Unit | entrant total above the cap scales down and warns |
| Property | shares sum to 1.0 at every year, for random entrant sets |
| Property | incumbent shares are non-increasing in entrant total share |
| Integration | a cheaper entrant raises incremental budget impact; a dearer one lowers it |
| Integration | projection off produces exactly the current-market result |

## 11. Acceptance criteria

- [x] Expected entry derived from primary completion plus a stated, named regulatory lag
- [x] Entrants ramp from their entry year and only from their entry year
- [x] Incumbent shares rescale proportionally and shares sum to 1.0 at every year
- [x] Projection is off by default and warns by name when enabled
- [x] Results are reported beside the current-market base case, not instead of it
- [x] An unpromoted entrant cannot be modelled

## 12. Assumptions & open questions

**Assumptions.** A 1.5-year regulatory lag applies uniformly; it does not. Trial success is assumed
for any entrant admitted, which is the single largest unstated optimism in the module — Phase III
attrition in metabolic disease is material, and the honest reading of a modelled entrant is
"conditional on approval". Plateau shares are analyst assumptions with no empirical basis in this
system.

**Open questions.**
1. Whether to weight an entrant's share by a phase-conditional probability of success rather than
   admitting it whole. It would be more defensible and it needs a source for the probability that
   this system does not currently have.
2. Whether an entrant should displace preferentially within its own mechanism class rather than
   proportionally across all incumbents. Clinically plausible; unsupported by any retrievable data.
