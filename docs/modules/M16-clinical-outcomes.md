# M16 — Clinical Outcomes and Avoided Events

Module specification v1.0 · Owner area: Engine + Backend · Depends on: M2, M5, M6, M7

---

## 1. Purpose

Turn an observed treatment effect into the events it avoids and the cost those avoided events
would have carried.

Budget impact without outcomes is half an argument. A payer asked to fund a therapy at $8,800
net per switched patient will ask what the $8,800 buys, and "weight loss" is not something a
budget holder can act on. Avoided incident diabetes, avoided cardiovascular events and the
hospitalisations that come with them are.

## 2. Scope

**In scope.** Response rates and the fraction of treated patients reaching a stated weight-loss
threshold; relative risk reduction per event class; events avoided per year; the unit cost of an
avoided event; the resulting cost offset; weight regain across the horizon.

**Out of scope.** Predicting an effect. Every response rate and risk reduction is supplied with
the trial it came from, and a subgroup with no supplied effect produces no avoided events — not
an interpolated one. Quality-adjusted life years and cost-effectiveness: this is a budget impact
model over 3–5 years, and a lifetime QALY model is a different instrument with different rules.
Mortality benefit beyond the horizon.

## 3. Dependencies

**Upstream.** M2 for the treated population; M6 for the persistence fraction, since an effect
only accrues while a patient is on therapy; M18 for the subgroup an effect belongs to.

**Downstream.** The cost offset feeds M5's `offset` per therapy, and therefore M7's two-world
subtraction and M13's cost bridge. Events avoided are reported in their own right.

## 4. Contracts

```python
class EventClass(StrEnum):
    INCIDENT_T2D = "incident_t2d"
    MACE = "mace"                    # CV death, non-fatal MI, non-fatal stroke
    HOSPITALISATION = "hospitalisation"
    OSA_PROGRESSION = "osa_progression"
    HYPERTENSION = "hypertension"


class ResponseThreshold(StrEnum):
    WL_5 = "wl_5"                    # >= 5% body weight lost
    WL_10 = "wl_10"
    WL_15 = "wl_15"


class TreatmentEffect(BaseModel):
    """One therapy's effect on one event class, in one subgroup."""

    model_config = ConfigDict(frozen=True)

    drug_id: int
    event: EventClass
    baseline_rate: Valued            # annual event rate on current care
    relative_reduction: Valued       # [0, 1) — 0.20 means a 20% relative reduction
    unit_cost: Money                 # cost of one event, this market


class ResponseProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    drug_id: int
    threshold: ResponseThreshold
    responder_share: Valued          # fraction reaching the threshold
    mean_weight_loss_pct: Valued
    #: Annual proportional loss of the achieved effect. M16 section 5.4.
    regain_per_year: Valued


class AvoidedEvents(BaseModel):
    model_config = ConfigDict(frozen=True)

    event: EventClass
    year: int
    events_without: float
    events_with: float
    avoided: float
    cost_avoided: Money


class OutcomeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    responders: tuple[float, ...]            # per year
    mean_weight_loss_pct: float
    avoided: tuple[AvoidedEvents, ...]
    total_cost_avoided: tuple[Money, ...]    # per year
    warnings: tuple[Warning_, ...]
```

```python
# biet_engine/outcomes.py — pure
def project_outcomes(
    treated_on_new: Sequence[float],
    effects: Sequence[TreatmentEffect],
    profile: ResponseProfile | None,
    *, persistence: float, country_code: str, currency: str,
) -> OutcomeResult: ...
```

## 5. Logic specification

### 5.1 Effects are supplied, never inferred

A `TreatmentEffect` carries a baseline rate, a relative reduction and the trial both came from.
Nothing derives one from a drug class, from a mechanism, or from another therapy's effect. A
therapy with no supplied effect avoids no events, and the result says so with
`NO_OUTCOME_EVIDENCE` rather than returning zero silently — zero avoided events and no evidence
about avoided events are different claims.

### 5.2 Responders

```
Responders(y) = TreatedOnNew(y) × responder_share × f
```

where `f` is M6's persistence fraction. An effect accrues only while a patient is on therapy;
counting a discontinued patient as a responder overstates both the clinical and the economic
result.

`responder_share` is the trial's own proportion reaching the threshold — for semaglutide 2.4 mg
at ≥5% body weight, STEP 1 reports it directly, so it is an observation rather than a model
output.

### 5.3 Events avoided

For event class `e`, in year `y`:

```
Events_without(e,y) = ExposedPatients(y) × baseline_rate(e)

Events_with(e,y)    = ExposedPatients(y) × baseline_rate(e) × (1 − rr(e) × effect_retained(y))

Avoided(e,y)        = Events_without(e,y) − Events_with(e,y)
                    = ExposedPatients(y) × baseline_rate(e) × rr(e) × effect_retained(y)
```

`ExposedPatients(y)` is patients on the new therapy adjusted for persistence, not the headline
uptake figure. `rr` is the relative reduction — for cardiovascular events in obesity without
diabetes, SELECT (NCT03574597, 17,604 participants) is the citable source, and its composite
MACE endpoint is what `EventClass.MACE` means here rather than a broader definition.

**Baseline rate is a property of the subgroup, not of the therapy.** Obesity with established
cardiovascular disease carries a materially higher annual MACE rate than obesity alone, and
applying one averaged rate across both produces a number describing neither. M18 is what makes
the distinction available; this module refuses to average across it.

### 5.4 Weight regain

Effect does not hold flat across a five-year horizon. `regain_per_year` is the annual
proportional loss of the achieved effect:

```
effect_retained(y) = (1 − regain_per_year) ^ (y − 1)
```

so the effect is full in year 1 and decays thereafter. Set `regain_per_year = 0` for a scenario
that assumes a maintained effect, which is a defensible assumption while on continuous therapy
and should be stated as one. The decay applies to the *event* reduction and to weight loss
alike, since the second is what drives the first.

### 5.5 Cost avoided, and where it goes

```
CostAvoided(y) = Σ(e) Avoided(e,y) × unit_cost(e)
```

per patient this becomes M5's `offset` for the new therapy, which flows into `AC(n,c)` and
therefore into M7's incremental impact and M13's bridge. It is not a separate line added at the
end: an avoided cost is part of the annual cost of the therapy that avoided it, and adding it
anywhere else would double-count against the offset M5 already accepts.

**Only offsets the payer actually bears count.** A hospitalisation avoided is a cost avoided for
an insurer and for a health system; productivity gain is neither, and belongs to M17's
perspective rather than here.

### 5.6 The claim this module is allowed to make

"When trial evidence establishes a treatment effect, its economic consequences are modelled" —
never "this therapy will avoid *n* events". Every avoided event is conditional on a supplied
effect, and the output reports the trial alongside the number so that a reader disputing the
number knows exactly which evidence to dispute.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| `relative_reduction` outside [0, 1) | Rejected — a reduction of 1.0 claims total prevention |
| `baseline_rate` outside [0, 1] | Rejected |
| No effect supplied for a therapy | No avoided events, `NO_OUTCOME_EVIDENCE` warning |
| No response profile supplied | Responders is `None`, not zero |
| `regain_per_year` of 0 | Effect maintained; stated as an assumption in the register |
| Persistence of 0 | No exposed patients, so no avoided events — arithmetically and clinically right |
| Effect supplied for a comparator, not the new therapy | Permitted: the comparator's avoided events reduce the world-without cost |
| Unit cost in the wrong currency | `CurrencyMismatchError` |
| Horizon longer than the trial's follow-up | `EFFECT_BEYOND_FOLLOW_UP` naming the trial's duration |

## 7. Data requirements

Creates `treatment_effects` (drug, subgroup, event class, baseline rate, relative reduction,
trial, follow-up weeks, tier) and `event_costs` (event class, market, unit cost, source).
Extends `drug_regimens` with nothing — response profiles live in their own table keyed on drug
and threshold.

Seeds: STEP 1 for response, SELECT for MACE, and published incidence for baseline rates.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/reference/event-costs` | Catalogue with per-market unit costs |
| GET | `/api/v1/reference/treatment-effects` | `?indication_id=&subgroup=` |

Outcomes are embedded in the forward calculation response per market; they explain a number that
response already contains.

## 9. Frontend

Slice `features/outcomes/`.

- `OutcomesPanel` — responders, events avoided and cost avoided per year
- `EventLedger` — event class, baseline rate, relative reduction, trial, follow-up
- Every figure states its trial inline; a row with no trial cannot exist
- `NO_OUTCOME_EVIDENCE` renders as a stated absence, not an empty table

## 10. Test specification

| Class | Test |
|---|---|
| Unit | avoided events equal exposed × baseline × rr, hand-computed |
| Unit | responders scale with persistence, not with headline uptake |
| Unit | `regain_per_year = 0` holds the effect flat across the horizon |
| Unit | regain of 0.2 retains 0.8 in year 2 and 0.64 in year 3 |
| Unit | no supplied effect yields no avoided events plus `NO_OUTCOME_EVIDENCE` |
| Unit | zero persistence yields zero avoided events |
| Unit | mismatched currency raises `CurrencyMismatchError` |
| Property | avoided events are never negative, for any admissible input |
| Property | avoided events are monotonically non-decreasing in relative reduction |
| Golden | cost avoided flows into M5's offset and reduces M7's incremental impact by exactly that amount |
| Integration | two subgroups with different baseline rates produce different avoided events |

## 11. Acceptance criteria

- [ ] Events avoided computed from a supplied baseline rate and relative reduction
- [ ] Every effect carries the trial it came from, and none is inferred
- [ ] Responders reflect persistence, not headline uptake
- [ ] Weight regain decays the effect across the horizon
- [ ] Cost avoided reaches M7 through M5's offset, not as a separate line
- [ ] A therapy with no evidence produces a stated absence, not a zero
- [ ] Baseline rates are per subgroup and never averaged across them

## 12. Assumptions & open questions

**Assumptions.** A constant annual baseline rate within the horizon. Relative reduction applies
uniformly across the eligible population rather than varying by baseline risk, which understates
benefit in high-risk subgroups and overstates it in low-risk ones — the reason §5.3 insists on
per-subgroup rates. Effect accrues only while on therapy, with no legacy benefit after
discontinuation; over 3–5 years that is conservative and defensible.

**Open questions.**
1. Whether avoided events should carry a time-to-event lag. A cardiovascular event avoided in
   year 1 of therapy is optimistic; SELECT's curves separate after roughly a year.
2. Whether to model events avoided in the *comparator* arm explicitly rather than through the
   baseline rate, which would matter if two comparators differ materially in effect.
