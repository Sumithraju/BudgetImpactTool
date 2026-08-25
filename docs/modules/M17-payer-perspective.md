# M17 — Payer Perspective and Decision Views

Module specification v1.0 · Owner area: Backend + Frontend · Depends on: M2, M7, M8, M9

---

## 1. Purpose

Frame the same computation for the budget holder who is actually reading it, and produce the
three summary figures a payer conversation opens with.

An insurer covering four million lives, a self-insured employer covering forty thousand and a
national health system are looking at different denominators and count different costs. A single
national figure answers none of their questions. This module makes the denominator an input,
converts impact to per-member-per-month, solves for the price at which impact reaches zero, and
puts low, medium and high uptake side by side.

## 2. Scope

**In scope.** The perspective taxonomy and what each perspective counts; covered population as
an input distinct from national population; PMPM alongside PMPY; break-even price; the low,
base and high uptake triplet.

**Out of scope.** Cost-effectiveness — a cost per QALY is a different instrument. The solver
itself: M8 owns the search, and M17 supplies it a different target. Estimating indirect costs
from first principles; where an employer perspective includes them they are supplied, with a
source, like every other value.

## 3. Dependencies

**Upstream.** M2 for the funnel, whose first stage this module replaces with covered lives;
M7 for incremental impact per year; M8 for the reverse solver; M9 for the uptake sweep
machinery. M18 supplies the subgroup breakdown that aggregates into these figures.

**Downstream.** M10's narrative and export lead with these numbers. M21 renders them as the
headline view.

## 4. Contracts

```python
class PayerPerspective(StrEnum):
    COMMERCIAL_INSURER = "commercial_insurer"
    SELF_INSURED_EMPLOYER = "self_insured_employer"
    GOVERNMENT_PAYER = "government_payer"
    HEALTH_SYSTEM = "health_system"


class CoverageBasis(StrEnum):
    EXPLICIT = "explicit"                # analyst supplied a covered-lives count
    NATIONAL_SHARE = "national_share"    # a stated share of the national population
    NATIONAL_TOTAL = "national_total"    # the whole market, for a health system


class CoveredPopulation(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    covered_lives: int                   # the denominator every per-member figure divides by
    basis: CoverageBasis
    share_of_national: float | None = None
    provenance: Provenance


class PerspectiveConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    perspective: PayerPerspective
    covered: CoveredPopulation
    include_indirect_costs: bool = False
    months_per_year: int = MONTHS_PER_YEAR       # 12; named, never inline


class UptakeBand(StrEnum):
    LOW = "low"
    BASE = "base"
    HIGH = "high"


class BandResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    band: UptakeBand
    peak_uptake: float
    impact_by_year: tuple[Money, ...]
    cumulative_impact: Money
    pmpm_by_year: tuple[Money, ...]


class DecisionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    perspective: PayerPerspective
    covered_lives: int
    pmpy_by_year: tuple[Money, ...]
    pmpm_by_year: tuple[Money, ...]
    cumulative_pmpm: Money
    break_even_price: Money | None
    break_even_status: BreakEvenStatus
    bands: tuple[BandResult, ...]
    warnings: tuple[Warning_, ...]
```

```python
# biet_engine/perspective.py — pure
def to_decision_view(
    impact: ImpactResult,
    config: PerspectiveConfig,
    bands: Sequence[BandResult],
    break_even: Money | None,
    status: BreakEvenStatus,
) -> DecisionView: ...
```

The service layer resolves covered lives, runs the engine once per band, calls M8 for the
break-even solve, and hands the assembled parts to this pure function. No I/O crosses into
`biet_engine`.

## 5. Logic specification

### 5.1 The perspective selects the denominator

The funnel's first stage is the covered population, not the national one. An insurer with four
million covered lives runs the whole of M2 on four million: adult share, prevalence, diagnosis,
treatment, eligibility and access all apply unchanged beneath it.

| Perspective | Default basis | Denominator |
|---|---|---|
| Commercial insurer | `EXPLICIT` | Enrolled lives, supplied |
| Self-insured employer | `EXPLICIT` | Covered employees and dependants, supplied |
| Government payer | `NATIONAL_SHARE` | Population under the public scheme |
| Health system | `NATIONAL_TOTAL` | National population from M0 |

Scaling a national result down by a coverage share is **not** equivalent and is not permitted.
It would carry the national comorbidity mix, the national comparator mix and the national
access rate into a population that has none of them, and it silently discards the reason the
perspective was chosen.

### 5.2 The perspective decides what counts as a cost

| Perspective | Direct medical | Pharmacy | Indirect (absence, productivity) | Public programme administration |
|---|---|---|---|---|
| Commercial insurer | yes | yes | no | no |
| Self-insured employer | yes | yes | **yes, if supplied** | no |
| Government payer | yes | yes | no | yes |
| Health system | yes | yes | no | yes |

`include_indirect_costs = True` on any perspective other than the employer is rejected rather
than ignored. A productivity gain is real and is not a line in an insurer's budget; admitting it
there inflates the offset with money that payer never sees.

### 5.3 Per-member-per-month

```
PMPY(y) = ΔBI(y) / covered_lives
PMPM(y) = ΔBI(y) / (covered_lives × months_per_year)
```

`cumulative_pmpm` divides cumulative impact by covered lives and by the total months in the
horizon — it is the mean monthly figure over the horizon, not the sum of the annual ones.

Three presentation rules follow the arithmetic and are part of this contract:

- **PMPM is reported to four decimal places.** A real PMPM lands in cents; rounding to two
  turns a defensible 0.0043 into 0.00 and destroys the only number some payers will read.
- **The sign convention is stated on the figure.** Positive is added cost to the payer.
- **PMPM is never averaged across markets or subgroups.** It is recomputed from summed impact
  over summed covered lives. Averaging ratios across unequal denominators is wrong, and the
  error grows with the spread between them.

### 5.4 Break-even price

The break-even price is M8's reverse solve with the target changed: instead of the price at
which the affordability ratio meets a threshold, it is the price at which cumulative incremental
impact equals zero. The search, the bounds and the convergence criteria are M8's and are not
reimplemented here.

Zero incremental impact is not zero cost. It is the price at which what the payer spends on the
new therapy, net of what it displaces and of the events it avoids, equals what the payer would
have spent anyway. Four outcomes are possible and each is reported distinctly:

```python
class BreakEvenStatus(StrEnum):
    SOLVED = "solved"                  # a positive price exists; reported
    ALREADY_COST_SAVING = "already_cost_saving"   # impact <= 0 at the current price
    UNREACHABLE = "unreachable"        # impact stays positive at a price of zero
    NOT_ATTEMPTED = "not_attempted"    # no priced new therapy in the scenario
```

`ALREADY_COST_SAVING` reports the headroom — how far the price could rise before impact turns
positive — because that is the question the analyst is really asking in that case.
`UNREACHABLE` means non-drug costs alone exceed what is displaced; the price is not the lever,
and saying so is more useful than returning zero.

### 5.5 Low, base and high uptake

Three bands, each a **complete engine run**, never a scaled result.

| Band | Default peak uptake | Rationale |
|---|---|---|
| Low | base × 0.5 | Slow formulary placement, restrictive prior authorisation |
| Base | scenario value | The analyst's central assumption |
| High | base × 1.5, capped at the addressable ceiling | Rapid adoption, permissive access |

Multipliers are defaults and are editable per scenario. Scaling the base result by 0.5 and 1.5
instead of re-running gives a different and wrong answer as soon as anything in the chain is
non-linear in uptake — persistence-weighted exposure in M6, the averaged outcome offset in M16,
incumbent rescaling in M14 and any non-proportional displacement matrix in M4 all are. The cost
of three runs is three times 200 ms, which is not a reason to be wrong.

A band whose peak exceeds the addressable population is capped there and reports
`UPTAKE_BAND_CAPPED` naming the band; it is not silently clipped.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| `covered_lives` of 0 or negative | Rejected — every per-member figure would divide by zero |
| `covered_lives` exceeding the national population | Rejected, naming the market and both figures |
| `share_of_national` outside (0, 1] | Rejected |
| `basis = NATIONAL_SHARE` with no share supplied | Rejected |
| `include_indirect_costs` on a non-employer perspective | Rejected, `INDIRECT_COSTS_NOT_IN_PERSPECTIVE` |
| Covered lives unknown | PMPM and PMPY omitted, `NO_COVERED_POPULATION`; impact still reported |
| Break-even solve does not converge | `break_even_price = None`, status `UNREACHABLE`, warning names the bracket searched |
| High band capped at the addressable ceiling | `UPTAKE_BAND_CAPPED` |
| Covered population supplied for one market only, in a multi-market run | Per-member figures for that market only; others report `NO_COVERED_POPULATION` |
| Perspective changed after a run | New run. Runs are immutable |

## 7. Data requirements

Creates `covered_populations`: market, perspective, covered lives, basis, share of national,
source, vintage, tier. Seeded with a defensible reference value per market for the government
and health-system perspectives — the national population and the public-scheme enrolment where
published — and left empty for insurer and employer, which are properties of the client, not of
the country. An empty row is correct there; a placeholder is not.

`PerspectiveConfig` is persisted with the run alongside the resolved inputs, so a stored result
can always be re-read against the denominator that produced it.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/reference/perspectives` | Taxonomy, what each counts, seeded covered lives |
| POST | `/api/v1/calculate/decision-view` | Impact plus PMPM, break-even and the three bands |

The forward calculation response gains a `decision_view` block per market when a
`PerspectiveConfig` is present on the scenario. It is not a separate call in the common path —
a payer reading the result should not have to ask for the payer view.

## 9. Frontend

Slice `features/payer-view/`.

- `PerspectiveSelector` — four options, each showing what it counts and what denominator it uses
- `CoveredLivesInput` — with the national population beside it as a sanity anchor
- `PmpmCard` — PMPM and PMPY, four decimals, sign convention stated on the card
- `BreakEvenCard` — the price, or the reason there is not one, in words
- `UptakeBandChart` — three trajectories, base emphasised, low and high as a band

## 10. Test specification

| Class | Test |
|---|---|
| Unit | PMPM equals impact over covered lives over twelve, hand-computed |
| Unit | `cumulative_pmpm` uses total months, not the sum of annual PMPMs |
| Unit | indirect costs on an insurer perspective are rejected |
| Unit | covered lives above national population are rejected |
| Unit | zero covered lives are rejected before any division |
| Unit | each `BreakEvenStatus` is produced by a scenario that warrants it |
| Unit | a band exceeding the addressable ceiling is capped and warns |
| Property | PMPM is monotonically decreasing in covered lives, for positive impact |
| Property | the base band result equals the plain forward calculation exactly |
| Golden | insurer at 4 M lives and health system at national both reproduce their fixture |
| Golden | break-even price re-run through the forward model yields cumulative impact of zero to within tolerance |
| Integration | PMPM across two markets is recomputed from totals, not averaged — the two differ, and the test asserts which is returned |

## 11. Acceptance criteria

- [ ] The funnel runs on covered lives, not on a scaled national result
- [ ] Each perspective admits exactly the cost categories §5.2 gives it
- [ ] PMPM and PMPY are reported per year and cumulatively, to four decimal places
- [ ] Break-even price is solved by M8 with a zero target, and its four outcomes are distinct
- [ ] Low, base and high are three complete runs
- [ ] A missing covered-lives figure suppresses per-member output rather than guessing one
- [ ] `PerspectiveConfig` is persisted with the run

## 12. Assumptions & open questions

**Assumptions.** Covered lives are constant across the horizon unless the scenario supplies a
growth rate; enrolment churn is out of scope. The eligible fraction within a covered population
matches the national one — true for a large insurer, less so for an employer population skewed
by age and occupation, which is the reason `CoveredPopulation` carries provenance and an
employer scenario should override the funnel rates rather than accept the national defaults.

**Open questions.**
1. Whether an employer perspective should carry a distinct default age structure, which would
   change adult share and prevalence together.
2. Whether break-even should be solvable against net price or list price when a gross-to-net
   assumption is in force — the two differ by the rebate, and payers negotiate on one of them.
3. Whether the low and high bands should also vary persistence, which correlates with uptake in
   practice; currently they vary uptake alone, which understates the spread.
