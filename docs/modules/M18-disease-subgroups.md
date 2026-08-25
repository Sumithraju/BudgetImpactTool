# M18 — Disease Subgroups

Module specification v1.0 · Owner area: Backend · Depends on: M2, M3, M4, M16

---

## 1. Purpose

Replace the list of indications with one disease and the clinically distinct populations inside
it.

Obesity with established cardiovascular disease is not obesity with type 2 diabetes, and neither
is obesity alone. They differ in how many people are in them, in what fraction is eligible, in
what they are currently treated with, in how fast a new therapy is taken up, and — most
consequentially — in the events a therapy avoids. Modelling them as one average population
produces a number that describes nobody, and it is precisely the high-risk subgroups where a
payer's money is made or lost.

## 2. Scope

**In scope.** The subgroup taxonomy for obesity; the mutually exclusive allocation of the
diseased population across it; per-subgroup epidemiology, eligibility, comparator mix, uptake
and outcome profile; aggregation of segment results into a scenario total; the paediatric
population as a separate denominator.

**Out of scope.** Other diseases. The tool narrows to obesity for this release, and a second
disease is a seeding exercise against this same structure rather than a change to it. Individual
patient simulation — a subgroup is a cohort, not a microsimulation. Transitions between
subgroups over the horizon: a patient who develops diabetes in year 3 stays in the subgroup they
started in, and §12 records what that costs.

## 3. Dependencies

**Upstream.** M2 for the funnel each subgroup runs through; M3 for the criteria that vary by
subgroup; M0 for per-subgroup prevalence seeds.

**Downstream.** M16 attaches an outcome profile per subgroup — the reason this module exists at
all, since baseline event rates differ by an order of magnitude across them. M7 aggregates. M17
computes per-member figures from the aggregate, never from a segment mean.

## 4. Contracts

```python
class Subgroup(StrEnum):
    """Adult subgroups are mutually exclusive and exhaustive. Paediatric is disjoint."""

    OBESITY_ESTABLISHED_CVD = "obesity_established_cvd"
    OBESITY_T2D = "obesity_t2d"
    OBESITY_HYPERTENSION = "obesity_hypertension"
    OBESITY_DYSLIPIDAEMIA = "obesity_dyslipidaemia"
    OBESITY_ALONE = "obesity_alone"
    PAEDIATRIC_OBESITY = "paediatric_obesity"


#: Allocation order for section 5.2. Highest clinical risk first.
SUBGROUP_PRIORITY: Final[tuple[Subgroup, ...]] = (
    Subgroup.OBESITY_ESTABLISHED_CVD,
    Subgroup.OBESITY_T2D,
    Subgroup.OBESITY_HYPERTENSION,
    Subgroup.OBESITY_DYSLIPIDAEMIA,
    Subgroup.OBESITY_ALONE,
)


class SubgroupProfile(BaseModel):
    """Everything that varies by subgroup. Anything absent falls back to the disease default."""

    model_config = ConfigDict(frozen=True)

    subgroup: Subgroup
    country_code: str
    share_of_diseased: Valued                      # of the adult obesity population
    diagnosis_rate: Valued | None = None
    treatment_rate: Valued | None = None
    access_rate: Valued | None = None
    criteria: tuple[Criterion, ...] = ()
    comparator_mix: tuple[MarketShare, ...] = ()
    uptake: UptakeInput | None = None
    effects: tuple[TreatmentEffect, ...] = ()
    response: ResponseProfile | None = None


class SegmentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    subgroup: Subgroup
    country_code: str
    funnel: FunnelResult
    impact: ImpactResult
    outcomes: OutcomeResult | None
    share_of_total_impact: float


class AggregateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    segments: tuple[SegmentResult, ...]
    total_impact_by_year: tuple[Money, ...]
    total_patients_by_year: tuple[float, ...]
    warnings: tuple[Warning_, ...]
```

```python
# biet_engine/subgroups.py — pure
def allocate_shares(
    profiles: Sequence[SubgroupProfile], *, strict: bool = True
) -> tuple[dict[Subgroup, float], tuple[Warning_, ...]]: ...

def aggregate_segments(
    segments: Sequence[SegmentResult], *, currency: str
) -> AggregateResult: ...
```

**The engine is not changed.** `compute_funnel`, `project_uptake`, `compute_impact` and
`project_outcomes` keep the signatures they have. The service layer loops over subgroups, calls
the existing engine once per segment with that segment's resolved inputs, and passes the results
to `aggregate_segments`. This is what makes a subgroup a scenario dimension rather than a new
engine contract, and it is why `biet_engine` stays pure.

## 5. Logic specification

### 5.1 The subgroup taxonomy

| Subgroup | Definition | Why it is separate |
|---|---|---|
| Obesity with established CVD | BMI ≥ 30 with prior myocardial infarction, stroke or symptomatic peripheral arterial disease | Highest baseline MACE rate; the population where an avoided event is worth most |
| Obesity with type 2 diabetes | BMI ≥ 30 with diagnosed T2D | Different current care entirely — already on glucose-lowering therapy, so the displaced cost is large |
| Obesity with hypertension | BMI ≥ 30 with diagnosed hypertension, no T2D, no established CVD | Large, cheaply treated today, so displaced cost is small |
| Obesity with dyslipidaemia | BMI ≥ 30 with diagnosed dyslipidaemia and none of the above | As above, on statin therapy |
| Obesity alone | BMI ≥ 30 with none of the above | Lowest event rate; the subgroup where a payer is least likely to fund |
| Paediatric obesity | Age under 18, BMI at or above the 95th centile for age and sex | Separate denominator, separate label, separate evidence base |

Two definitional notes that matter and that a reader will otherwise get wrong.

**"Cardiac arrest" is an event, not a population.** The review named it; the modellable
population is established atherosclerotic cardiovascular disease, and cardiac arrest is one of
the events this subgroup has an elevated rate of. The subgroup is the population; the arrest is
in M16's `EventClass`.

**"BMI over 30 in children" is not the paediatric definition.** In adults obesity is a fixed
BMI cut-off; in children BMI varies with age and sex, and obesity is defined at or above the
95th centile (CDC) or above +2 standard deviations (WHO growth reference). Applying the adult
cut-off to a twelve-year-old identifies a far smaller and much sicker group than the label
suggests. The subgroup uses the centile definition and the interface says so where it is chosen.

### 5.2 Allocation is exclusive, and the shares sum to one

A patient with obesity, type 2 diabetes and hypertension exists in every prevalence statistic
for all three. Adding those prevalences counts them three times. The five adult subgroups
therefore partition the adult obesity population: each patient is allocated to the **first**
subgroup in `SUBGROUP_PRIORITY` whose definition they meet, and `OBESITY_ALONE` takes the
remainder.

```
share(OBESITY_ALONE) = 1 − Σ share(s) for s in the four comorbidity subgroups
```

`allocate_shares` asserts that the four supplied shares sum to strictly less than 1.0 and
derives the fifth. Supplying all five is rejected: the residual is arithmetic, not an input, and
letting both be supplied invites a set that does not sum to one.

`strict=True` rejects a comorbidity total at or above 1.0. `strict=False` — used only by M9's
sensitivity sweeps, matching M3's precedent — normalises and returns `SUBGROUP_SHARES_NORMALISED`
rather than raising, so a sweep that pushes one share high does not abort the analysis.

**Paediatric obesity is disjoint.** It is not part of the adult partition and does not enter
that sum. Its denominator is the under-18 population times paediatric obesity prevalence, both
resolved independently. A run that includes it adds a segment; it does not take patients from
any other segment.

### 5.3 Every segment runs the whole model

Each subgroup carries its own resolved values for the entire chain:

```
share_of_diseased → diagnosis → treatment → criteria → access
                  → uptake → persistence → comparator mix → cost
                  → outcome profile → impact
```

Anything the profile leaves as `None` falls back to the disease-level default, and the
resolution level is recorded per value exactly as §7.3 requires — a subgroup override is a
fourth resolution level below scenario override, reported as such and never silently merged
into the country value.

The comparator mix is the field where this matters most and the one most often left as a
default by mistake. A patient with obesity and type 2 diabetes is already on metformin and
possibly on an SGLT2 inhibitor; a patient with obesity alone is on a lifestyle programme or on
nothing. Applying one mix to both overstates displaced cost in the second and understates it in
the first, and those two errors do not cancel.

### 5.4 Aggregation, and what must never be averaged

| Quantity | Aggregation |
|---|---|
| Patients, per stage and per year | Sum across segments |
| Cost with, cost without, incremental impact | Sum across segments, same currency asserted |
| Events avoided, cost avoided | Sum across segments |
| Cost per treated patient | Total impact ÷ total treated. **Not** a mean of segment values |
| PMPM, PMPY | Recomputed by M17 from totals. **Not** a mean of segment values |
| Any rate — diagnosis, uptake, persistence | Patient-weighted mean, and reported as a derived figure |
| Confidence tier | The weakest tier present in any contributing segment |

The rule underneath the table: **a ratio is aggregated by recomputing it from its aggregated
numerator and denominator, never by averaging the segment ratios.** Segment sizes differ by
more than an order of magnitude between established CVD and obesity alone, so an unweighted
mean of two segment PMPMs is not approximately right — it is wrong by roughly the size ratio.

`share_of_total_impact` per segment is reported so the analyst can see which population is
driving the answer. In a typical obesity scenario, two subgroups produce most of the impact and
the interface should not make that discovery difficult.

### 5.5 What a subgroup breakdown is allowed to claim

That the modelled populations differ in the ways the supplied inputs say they differ. Where a
subgroup has no supplied outcome evidence, M16's `NO_OUTCOME_EVIDENCE` applies per segment —
the segment contributes cost and no avoided events, and the aggregate says which segments those
were. An aggregate that quietly averages a subgroup with evidence and one without would report a
diluted effect as though it were measured, and it must not.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| Comorbidity shares summing to ≥ 1.0 | `strict=True` raises; `strict=False` normalises and warns |
| A share outside [0, 1] | Rejected |
| All five adult shares supplied | Rejected — `OBESITY_ALONE` is derived |
| Paediatric share included in the adult sum | Rejected — it has its own denominator |
| No subgroups selected | The run proceeds as a single undifferentiated obesity population, warning `NO_SUBGROUP_BREAKDOWN` |
| One subgroup selected | Valid. The result is that subgroup, and it is not labelled a total |
| A subgroup with no comparator mix | Falls back to the disease default, warning `SUBGROUP_MIX_DEFAULTED` naming the subgroup |
| A subgroup with no outcome evidence | Cost only, `NO_OUTCOME_EVIDENCE` naming the subgroup |
| Segments in mixed currencies | `CurrencyMismatchError` at aggregation |
| Paediatric subgroup with an adult-only therapy label | Rejected at scenario build, naming the label restriction |

## 7. Data requirements

Creates `disease_subgroups` (code, disease, definition, clinical note, paediatric flag) and
`subgroup_prevalence` (market, subgroup, share of diseased, source, vintage, tier).

Seeding, and its honest state: comorbidity co-prevalence within an obese population is published
per market for type 2 diabetes and hypertension in most of the ten markets, thinner for
dyslipidaemia, and thin everywhere for established CVD within obesity specifically. Seeds carry
the tier that reflects that — B where a national survey supports the figure, C where it is
derived from a regional analogue — and no share is seeded at tier A unless a country-specific
published figure exists. M15's evidence-gap ranking will surface these, which is the intended
outcome rather than an embarrassment: the tool should say that the split between subgroups is
one of the least certain things in the model, because it is.

Existing `indications` rows for type 2 diabetes are retained but no longer selectable as a
standalone disease; the T2D population enters as `OBESITY_T2D`. The migration is additive and
does not delete history — non-negotiable 9 applies to reference data as much as to runs.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/reference/subgroups` | Taxonomy with definitions and paediatric flag |
| GET | `/api/v1/reference/subgroups/{code}/prevalence` | `?country_code=`, with provenance |

Scenario payloads gain a `subgroups: list[SubgroupProfile]`. The calculation response gains
`segments` alongside the existing totals, so a client that ignores subgroups still reads a
correct total.

## 9. Frontend

Slice `features/subgroups/`.

- `SubgroupSelector` — the six, each with its definition in one sentence and its seeded share
- `ShareAllocator` — four editable shares with the residual shown live and non-editable
- `SegmentBreakdownTable` — patients, impact, events avoided and share of total per segment
- `SegmentContributionChart` — impact by segment, so the driver is visible without arithmetic
- The paediatric row is visually separated from the adult partition, because it is not in it

## 10. Test specification

| Class | Test |
|---|---|
| Unit | four shares summing to 0.62 derive `OBESITY_ALONE` at 0.38 |
| Unit | four shares summing to 1.05 raise under `strict=True` |
| Unit | the same shares normalise and warn under `strict=False` |
| Unit | supplying all five shares is rejected |
| Unit | paediatric share does not enter the adult partition sum |
| Unit | aggregate cost per treated patient is recomputed, not averaged — asserted against a hand-computed case where the two differ |
| Unit | a segment without a comparator mix falls back and warns by name |
| Property | total patients equal the sum of segment patients, for any admissible allocation |
| Property | aggregate impact is invariant to segment ordering |
| Golden | one obesity population split into five reproduces the same total as the undifferentiated run when every segment carries the disease defaults |
| Golden | moving 5 points of share from `OBESITY_ALONE` to `OBESITY_ESTABLISHED_CVD` increases avoided events and increases the offset |
| Integration | a subgroup with no outcome evidence contributes cost and no events, and the aggregate names it |

The first golden test is the important one. If splitting a population into segments that all
carry identical inputs changes the total, the aggregation is wrong, and that is the failure mode
this design is most exposed to.

## 11. Acceptance criteria

- [ ] One disease, six subgroups, with the adult five forming an exclusive partition
- [ ] `OBESITY_ALONE` is derived as the residual and cannot be supplied
- [ ] Paediatric obesity carries its own denominator and its own prevalence
- [ ] Every segment runs the full chain with its own resolved values
- [ ] `biet_engine` signatures are unchanged — a subgroup is a scenario dimension
- [ ] Ratios are recomputed from aggregated totals, never averaged across segments
- [ ] Segment contribution to total impact is reported
- [ ] A uniform split reproduces the undifferentiated total exactly

## 12. Assumptions & open questions

**Assumptions.** Subgroup membership is fixed for the horizon: a patient who develops type 2
diabetes in year 3 remains in the subgroup they entered in. Over three to five years this
understates the benefit of a therapy that prevents progression, since the prevented case never
moves the patient into a more expensive segment — M16 credits the avoided event, and this module
does not additionally move the patient. That is deliberate: crediting both would double-count.

The priority order in `SUBGROUP_PRIORITY` assumes established CVD dominates T2D clinically for
allocation purposes. A patient with both is counted once, in the CVD segment, and that segment's
comparator mix must therefore include glucose-lowering therapy or the displaced cost is
understated.

**Open questions.**
1. Whether `OBESITY_T2D` should split by insulin use, which changes displaced cost more than
   any other single distinction inside that subgroup.
2. Whether paediatric obesity should be modelled at all in the first release, given that label
   coverage and the evidence base are both thin — the alternative is to specify it, seed it at
   tier D and let M15 rank it as the gap it is.
3. Whether a second disease should reuse `Subgroup` as an open registry keyed on disease rather
   than a closed enum. The closed enum is right while there is one disease and wrong the moment
   there are two.
