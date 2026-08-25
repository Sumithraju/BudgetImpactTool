# M13 — Safety and Adverse-Event Economics

Module specification v1.0 · Owner area: Engine + Backend · Depends on: M5, M7, M12

---

## 1. Purpose

Convert an observed adverse-event profile into the adverse-event management cost M5 already
consumes, and decompose the net incremental cost per patient switched into the components that
produce it.

A payer does not compare acquisition prices. It compares total cost of care. A therapy priced above
the incumbent it displaces can be close to budget-neutral once avoided adverse-event management,
monitoring and administration are counted — and a therapy priced below it can still cost more. The
arithmetic is not difficult; what is difficult is doing it without asserting a clinical claim the
evidence has not established. This module does the arithmetic and refuses the claim.

## 2. Scope

**In scope.** The adverse-event catalogue and its per-market unit management costs; per-therapy
event profiles with incidence, exposure window, population and citation; annualisation; expected
annual adverse-event cost; the component decomposition of net cost per switch.

**Out of scope.** Predicting an adverse-event rate, inferring one from a drug class, or filling a
missing profile with a comparator's. Deriving persistence from tolerability (§5.5). Clinical
efficacy of any kind — this module prices events, it does not evaluate therapies.

## 3. Dependencies

**Upstream.** M12 for the `drug_id` a profile attaches to; M0's `countries` for market and currency;
M5's `TherapyInput.ae_cost`, which is what this module ultimately populates.

**Downstream.** M5 consumes the expected cost; M7's net cost per switch is what the bridge
decomposes; M9 varies incidences and unit costs like any other parameter; M10 reports the bridge.

## 4. Contracts

```python
class AdverseEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str                        # 'nausea', 'severe_hypoglycaemia'
    label: str
    is_serious: bool


class EventIncidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    event: AdverseEvent
    incidence: Valued                # fraction, as observed
    exposure_weeks: int | None       # None means the source reports an annual rate
    unit_cost: Money                 # cost of managing one occurrence, this market


class SafetyProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    drug_id: int
    country_code: str
    events: tuple[EventIncidence, ...]


class CostComponent(StrEnum):
    ACQUISITION = "acquisition"
    ADMIN = "admin"
    MONITORING = "monitoring"
    AE = "ae"
    OFFSET = "offset"


class BridgeTerm(BaseModel):
    model_config = ConfigDict(frozen=True)

    component: CostComponent
    new_therapy: Money               # f_n × k(n,c)
    displaced: Money                 # Σ σ_t × f_t × k(t,c)
    delta: Money                     # signed contribution to net cost per switch


class CostBridge(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    terms: tuple[BridgeTerm, ...]
    net_cost_per_switch: Money       # equals the signed sum of terms, exactly
```

```python
# biet_engine/safety.py — pure
def annualise(incidence: float, exposure_weeks: int | None) -> float: ...
def expected_ae_cost(profile: SafetyProfile) -> Money: ...
def build_cost_bridge(
    new: TherapyCost, comparators: Sequence[TherapyCost],
    *, substitution: Substitution, persistence: Mapping[int, float],
) -> CostBridge: ...
```

## 5. Logic specification

### 5.1 Evidence gating

An incidence enters the system only with a source, a vintage, an evidence type (trial, label or
literature), the population it was observed in, and a confidence tier. There is no default and no
inference. A drug class does not imply a rate; a comparator's profile is not a substitute for a
missing one.

Three conditions produce a warning rather than a value:

| Condition | Code | Why it matters |
|---|---|---|
| A therapy in the mix has no profile while another does | `AE_PROFILE_ASYMMETRIC` | Pricing the new therapy's events while leaving comparators at zero inflates its apparent cost — or, with the sides reversed, manufactures a saving |
| A profile's incidences come from a different population than the scenario models | `AE_POPULATION_MISMATCH` | An incidence observed in a diabetes trial is not an obesity incidence |
| Unit management cost is derived rather than observed for this market | `AE_COST_DERIVED` | Same class of caveat as a purchasing-power-derived price |

`AE_PROFILE_ASYMMETRIC` is the important one. The asymmetric case is the natural state of the data —
a new asset has a recent, detailed trial; a comparator approved in 2010 may have a label and little
else — and it biases in whichever direction the better-documented therapy sits. It is a warning, not
an error, because refusing to compute would be worse than computing with a stated caveat.

### 5.2 Expected adverse-event cost

```
AECost(t,c) = Σ(e ∈ E_t) [ p(e,t) × unit_cost(e,c) ]
```

with annualisation under constant hazard where the source reports over a window other than a year:

```
p(e,t) = 1 - ( 1 - p_obs(e,t) ) ^ ( 52 / exposure_weeks(e,t) )
```

The transformation is the identity at 52 weeks and is skipped when `exposure_weeks` is null. It
assumes constant hazard, which for events concentrated in a titration period overstates the later
part of the year; the assumption is stated wherever an annualised figure is displayed.

Currency is checked, not assumed: every `unit_cost` in a profile must be in the market's currency,
and a mismatch raises `CurrencyMismatchError` rather than summing two currencies into a plausible
number.

**Resolution order.** An observed `ae_cost` for a therapy in a market outranks a profile-derived
one, exactly as an observed price outranks a purchasing-power-derived price (§7.3). The derived
figure is used when no observed one exists, and is labelled derived.

### 5.3 The cost bridge

M7's net cost per switch is the bracketed term of the reduced-form budget impact:

```
NetCostPerSwitch(c) = f_n × AC(n,c) - Σ(t ∈ T) σ_t × f_t × AC(t,c)
```

`AC` is a sum of five components, so the term decomposes exactly, component by component:

```
Δ_k(c) = f_n × k(n,c) - Σ(t ∈ T) σ_t × f_t × k(t,c)
```

and the offset, which enters `AC` negatively, enters the bridge negatively:

```
NetCostPerSwitch(c) = Δ_acq + Δ_admin + Δ_monitoring + Δ_ae - Δ_offset
```

The identity holds by construction and is asserted as a test invariant rather than trusted. It is
the whole output of this module in one line: not what the new drug costs, but of the difference, how
much is price and how much is everything else.

A worked shape, for one switched patient:

```
Acquisition          +2,000     the new therapy costs more to buy
Administration         -100     fewer administrations
Monitoring             -300     less frequent laboratory monitoring
Adverse events         -800     lower expected event cost
Offsets                 -300     avoided events, subtracted
                     ────────
Net cost per switch    +500
```

The headline "$2,000 more expensive" and the decision-relevant "+500" are both true, and only the
second belongs in a budget impact.

### 5.4 Where the bridge sits relative to budget impact

The bridge is per switched patient. Multiplying by addressable population and uptake reproduces
M7's budget impact for the year exactly; the bridge adds no new arithmetic and must not diverge from
M7 by so much as a rounding step. A golden test asserts the reconciliation both ways.

### 5.5 Persistence is not derived from tolerability

Better tolerability plausibly lowers discontinuation, which raises persistence, which changes
exposure and therefore annual cost. Every link in that chain is defensible and the chain as a whole
is an inference. This system does not make it.

Persistence remains a separately sourced M6 input. A scenario may assume a tolerability-driven
persistence advantage — that is a legitimate analysis — but it is entered as an assumption, carries
its own tier, and appears in the assumption register as one. The supported statement is "when
evidence indicates a different adverse-event profile, its cost consequences are modelled", never
"this therapy will be better tolerated".

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| Incidence outside [0, 1] | Rejected at write and at load |
| `exposure_weeks <= 0` | Rejected — annualisation is undefined |
| Incidence of exactly 1.0 over a short window | Annualises to 1.0; no extrapolation beyond certainty |
| Unit cost in the wrong currency | `CurrencyMismatchError` |
| Therapy with no profile | Expected cost is the observed `ae_cost`, or zero with `AE_PROFILE_ASYMMETRIC` if any therapy in the mix has one |
| Empty event set | Expected cost zero — a real answer, distinct from "no profile" |
| Zero uptake | Bridge is still computable; budget impact is zero |
| Substitution vector entirely treatment-naive | Displaced side of every term is zero; net cost per switch is the new therapy's full cost |

## 7. Data requirements

Creates `adverse_events`, `adverse_event_costs` and `drug_adverse_events` (ARCHITECTURE.md §8.4).
Seeds the event catalogue for the therapy areas in scope, and unit management costs per market with
sources. Alembic migration required and reversible.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/comparators/assets/{id}/bridge` | Cost bridge against a nominated comparator basket and market |
| GET | `/api/v1/reference/adverse-events` | Catalogue with per-market unit costs |

The bridge is also embedded in the forward calculation response per market, since it explains a
number that response already contains.

## 9. Frontend

Slice `features/comparator-discovery/`.

- `CostBridgeChart` — waterfall from the new therapy's cost through each component to net cost per switch
- `SafetyComparisonTable` — event, incidence on each therapy, exposure window, unit cost, expected cost, source
- Every incidence displays its source and population inline; a row without one cannot exist
- `AE_PROFILE_ASYMMETRIC` renders as a banner on the comparison, not as a footnote

## 10. Test specification

| Class | Test |
|---|---|
| Unit | `annualise` is the identity at 52 weeks |
| Unit | 68-week incidence annualises below the observed figure; 26-week above it |
| Unit | annualising 1.0 returns 1.0 at any window |
| Unit | expected cost is Σ p × cost, hand-computed on a two-event profile |
| Unit | mismatched currency raises `CurrencyMismatchError` |
| Unit | observed `ae_cost` outranks a profile-derived one |
| Unit | a mix where one therapy has a profile and another does not emits `AE_PROFILE_ASYMMETRIC` |
| Property | bridge terms sum exactly to net cost per switch, for random inputs |
| Property | raising only the new therapy's adverse-event incidence never lowers budget impact |
| Golden | bridge × addressable × uptake reconciles to M7's budget impact for the year |
| Integration | two scenarios differing only in adverse-event profile produce different budget impact |

## 11. Acceptance criteria

- [x] Expected adverse-event cost computed from incidence and unit cost, annualised where needed
- [x] Every incidence carries source, vintage, evidence type, population and tier; none can be written without them
- [x] Asymmetric profiles warn rather than silently bias the comparison
- [x] The bridge sums exactly to net cost per switch, asserted as an invariant
- [x] The bridge reconciles to M7's budget impact with no divergence
- [x] Persistence is never inferred from an adverse-event profile

## 12. Assumptions & open questions

**Assumptions.** Constant hazard within the exposure window, which is the standard approximation and
is wrong in the direction stated in §5.2. One management cost per event per market, rather than a
severity distribution. Events are independent; a patient experiencing two events is charged for
both, which is right for management cost and wrong if the two would be managed in one consultation.

**Open questions.**
1. Whether serious events should be modelled with a severity split rather than a single unit cost.
   The catalogue's `is_serious` flag exists to make that change cheap later.
2. Whether discontinuation-driven events should be counted once per treated patient or once per
   patient-year. Currently per patient-year, which is consistent with the rest of the cost stack.
