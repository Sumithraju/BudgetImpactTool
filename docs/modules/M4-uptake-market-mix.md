# M4 — Uptake & Market Mix

Module specification v1.0 · Owner area: Engine · Depends on: M2, M3

---

## 1. Purpose

Project the share of the addressable population receiving the new therapy in each launch-relative
year, and the corresponding displacement of incumbent therapies. The displacement half is what
makes budget impact incremental rather than gross.

## 2. Scope

**In scope.** Three uptake curve families; the source-of-business substitution vector; baseline
(world-without) market shares; world-with shares after displacement; share-accounting invariants.

**Out of scope.** Cost per therapy (M5). Persistence (M6). The impact arithmetic itself (M7).

## 3. Dependencies

Consumes `FunnelResult.addressable` from M2 and the therapy set from M5. Produces `MarketMix`
consumed by M7.

## 4. Contracts

```python
class UptakeCurve(StrEnum):
    LINEAR = "linear"
    LOGISTIC = "logistic"
    MANUAL = "manual"


class UptakeInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    curve: UptakeCurve
    year_1: Valued | None = None            # linear
    terminal: Valued | None = None          # linear, logistic plateau
    steepness: Valued | None = None         # logistic k
    inflection_year: Valued | None = None   # logistic y_mid
    vector: tuple[float, ...] | None = None # manual
    allow_erosion: bool = False


class Substitution(BaseModel):
    model_config = ConfigDict(frozen=True)
    shares: Mapping[int, Valued]            # drug_id -> sigma, sums to 1.0


class MarketMix(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    year: int
    uptake: float                           # u(y), share of addressable
    shares_without: Mapping[int, float]     # drug_id -> m_without, sums to 1.0
    shares_with: Mapping[int, float]        # drug_id -> m_with; + uptake sums to 1.0


# biet_engine/uptake.py
def project_uptake(inputs: UptakeInput, horizon: int) -> tuple[float, ...]: ...
def build_market_mix(
    baseline: Mapping[int, Sequence[float]],   # drug_id -> per-year baseline share
    uptake: Sequence[float],
    substitution: Substitution,
    country_code: str,
) -> tuple[MarketMix, ...]: ...
```

## 5. Logic specification

### 5.1 Uptake curves

Per ARCHITECTURE.md §5.3. `y` is launch-relative, 1-indexed, `N` = horizon.

**Linear.**
```
u(y) = u₁ + (u_N − u₁) × (y − 1) / max(1, N − 1)
```
For `N = 1`, `u(1) = u₁`.

**Logistic.**
```
u(y) = u_max / (1 + exp(−k × (y − y_mid)))
```
Defaults `k = 1.2`, `y_mid = N / 2`. Note this does not start at zero: at `y = 1` with `N = 3`,
`u = u_max / (1 + exp(0.6)) ≈ 0.354 × u_max`. This is intended — a launch year with meaningful
early uptake. Teams wanting a near-zero start should raise `k` or `y_mid`, or use `manual`.

**Manual.** The supplied vector, validated to length `N` and each element in `[0, 1]`.

**Default selection.** Logistic for entry into an established competitive class; linear for
first-in-class entry into an untreated population.

### 5.2 Monotonicity

Uptake must be non-decreasing unless `allow_erosion = True`, which exists for competitive-erosion
scenarios where a later entrant takes share back. A decreasing vector without the flag raises
`UptakeMonotonicityError` — it is far more often a data-entry error than an intent.

### 5.3 Source of business

Where the new therapy's patients come from, as a vector over therapies:

```
Σ (t ∈ T) σ_t = 1,     σ_t ≥ 0
```

**Treatment-naive patients are modelled as a therapy.** The therapy set includes a
`no_pharmacotherapy` pseudo-entry with annual cost 0 and persistence 1.0. `σ_naive` is simply its
σ. This keeps the share accounting uniform and makes the sum-to-one invariant exact, rather than
carrying a special case through M7.

### 5.4 Displacement

```
m_with(t, y) = max(0, m_without(t, y) − u(y) × σ_t)
```

The floor at zero is reachable when a therapy's baseline share is smaller than the share the new
therapy draws from it. When it binds, the un-displaced remainder is **redistributed
proportionally** across the remaining therapies' σ so that the accounting still closes:

```python
def displace(m_without, u, sigma):
    deficit = 0.0
    m_with = {}
    for t, m in m_without.items():
        take = u * sigma[t]
        if take > m:
            deficit += take - m
            m_with[t] = 0.0
        else:
            m_with[t] = m - take
    if deficit > 0:
        headroom = {t: m for t, m in m_with.items() if m > 0}
        total = sum(headroom.values())
        if total <= 0:
            raise DisplacementError("no headroom to absorb displacement")
        for t, m in headroom.items():
            m_with[t] = m - deficit * (m / total)
    return m_with
```

A `SUBSTITUTION_FLOOR` warning is emitted whenever redistribution occurs, because it means the
stated source-of-business vector is inconsistent with the baseline mix and the user should revisit
one of them.

### 5.5 Baseline shares

`m_without(t, y)` defaults to constant across the horizon at the seeded baseline mix. A per-year
vector may be supplied per therapy via `therapy.<drug_id>.market_share.<year>`. Baseline shares
must sum to 1.0 (±1e-6) in every year.

### 5.6 Share accounting invariant

For every market and year:

```
u(y) + Σ (t ∈ T) m_with(t, y) = 1.0   (±1e-9)
```

Asserted in the engine. A violation is a defect in this module, not a data problem.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| `u(y)` outside `[0, 1]` | Raise `ValueError` |
| Decreasing uptake without `allow_erosion` | Raise `UptakeMonotonicityError` |
| Manual vector length ≠ horizon | Raise `ValueError` |
| σ sums ≠ 1 (±1e-6) | Raise `ValueError` |
| Any σ < 0 | Raise `ValueError` |
| Baseline shares sum ≠ 1 in any year | Raise `ValueError` |
| σ names a therapy not in the therapy set | Raise `UnknownTherapyError` |
| Displacement floor binds | Redistribute, warn `SUBSTITUTION_FLOOR` |
| No headroom to redistribute | Raise `DisplacementError` |
| `u(y) = 0` for all y | Valid; M7 must produce zero impact |
| `N = 1` | Linear and logistic must both be defined |

## 7. Data requirements

Baseline shares and σ are seeded per indication and market in `data/seed/`; both are commonly
overridden per scenario. Uptake parameters are scenario-level, not seeded per market, unless a
market-specific override is supplied.

## 8. API surface

None directly. Surfaces in the calculation response as `years[].uptake` and, when
`?include_mix=true`, the full share breakdown.

## 9. Frontend

Slice `features/market-uptake/`.

- `UptakeCurveEditor` — curve family selector; parameter inputs; live preview chart; switching to
  `manual` seeds the vector from the current curve so no work is lost
- `SubstitutionMatrix` — σ per therapy with a running total and an inline error until it sums to 1;
  a normalise action distributes the remainder proportionally
- `MarketMixChart` — stacked area of world-without versus world-with shares by year

Uptake is a fraction in state; the slider maps 0–100 to `0.0–1.0` at the input boundary.

## 10. Test specification

| Class | Test |
|---|---|
| Unit | linear, `u₁=0.05`, `u_N=0.15`, `N=3` → `(0.05, 0.10, 0.15)` |
| Unit | linear with `N=1` → `(u₁,)` |
| Unit | logistic, `u_max=0.15`, `k=1.2`, `y_mid=1.5`, `N=3` → y1 ≈ 0.0532, y3 ≈ 0.1287 |
| Unit | manual vector passes through unchanged |
| Unit | decreasing vector raises without `allow_erosion`, passes with it |
| Unit | displacement: `m=0.40`, `u=0.05`, `σ=0.60` → `m_with = 0.370` |
| Unit | floor binds: `m=0.01`, `u=0.05`, `σ=0.60` → 0.0, deficit redistributed, warning emitted |
| Unit | no headroom raises `DisplacementError` |
| Unit | σ summing to 0.99 raises |
| Property | `u(y) + Σ m_with(t,y) = 1` for all valid inputs |
| Property | uptake non-decreasing when `allow_erosion` is false |
| Property | every `m_with(t,y) ∈ [0, 1]` |

## 11. Acceptance criteria

- [ ] Pure; no I/O
- [ ] All three curve families implemented with the stated defaults
- [ ] Treatment-naive modelled as a zero-cost therapy, not a special case
- [ ] Displacement floors at zero and redistributes with a warning
- [ ] Share accounting invariant asserted and property-tested
- [ ] `mypy --strict` clean; 100% branch coverage on `uptake.py`

## 12. Assumptions & open questions

**Assumptions.** Source of business is constant across the horizon. Baseline mix is constant unless
explicitly overridden per year. Uptake applies uniformly across the addressable population — no
per-segment uptake (see M3 §12).

**Open question.** Whether competitive entry — a second new therapy arriving in year 2 or 3 —
needs modelling for launch. Currently expressible only through a manual uptake vector with
`allow_erosion`. A first-class competitor entry feature would change `UptakeInput` and is deferred.
