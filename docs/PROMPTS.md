# BIET — Implementation Prompts

One build prompt per phase. Each is written to be handed to an engineer or a coding agent with
nothing else in front of them, and to be finishable without coming back for clarification.

**These are not a substitute for the specifications.** Each prompt names what to read, and the
module spec is the contract. A prompt that disagrees with `docs/modules/` is a bug in the prompt;
a module spec that disagrees with `docs/ARCHITECTURE.md` loses to the architecture document.

Status of each phase lives in [STATUS.md](../STATUS.md), not here.

---

## The preamble

Prepend this to any phase prompt below. It is the part that is the same every time.

> You are working on BIET, an early-stage budget impact estimation tool for pharmaceutical
> pricing and market access. Read `CLAUDE.md` first, then `docs/ARCHITECTURE.md` §1–§4C for
> orientation and the sections your phase names.
>
> Working under `backend/` means following `.claude/skills/biet-backend/SKILL.md`. Working under
> `frontend/` means `.claude/skills/biet-frontend/SKILL.md`. Where a skill and the architecture
> document disagree, the architecture document wins.
>
> The ten non-negotiables in `CLAUDE.md` are not style preferences. The three that break most
> often in new work:
>
> - **The engine is pure.** `biet_engine` performs no I/O of any kind — no HTTP, no database, no
>   file access, no clock. Values are resolved before it is called. `backend/tests/test_layering.py`
>   enforces this with an AST check and will fail the build.
> - **Budget impact is incremental.** World-with minus world-without. Never the gross cost of the
>   new therapy, in a calculation, in an API response or on a screen.
> - **Provenance never drops.** Source, vintage and confidence tier travel with every value from
>   resolution to the interface and into every export. A transform that returns a bare `float`
>   where it received a `Valued` has lost something that cannot be recovered downstream.
>
> Do not invent a number. Every default, rate and price is seeded with a source and a confidence
> tier, and a value you cannot source is a tier D placeholder that says so — not a plausible
> figure typed into a constant.
>
> Finish against the phase's definition of done, run the checks, and report honestly what passes
> and what does not. A partial phase reported as complete costs more than an unfinished one.

**Definition of done, every phase.** `pytest` green, `mypy --strict` clean, `ruff` clean,
`test_layering.py` passing, new error codes in the registry rather than inlined, an Alembic
migration written and reversible if the schema changed, `biet_engine.__version__` bumped if
engine behaviour moved, and golden fixtures updated with a written justification if any result
changed. The full list is §12 of the backend skill.

---

## Phase 12 — Clinical Outcomes and Avoided Events

**State.** The engine module is built: `biet_engine/outcomes.py`, 20 unit tests and 5 property
tests. What remains is everything around it.

**Read.** `docs/modules/M16-clinical-outcomes.md`; ARCHITECTURE.md §5.10 and §4B.

**Build.**

1. `treatment_effects` and `event_costs` tables, with the Alembic migration. Effects are keyed on
   drug, subgroup and event class; every row carries its trial, follow-up duration and tier.
2. Seed from the trials the specification names — SELECT (NCT03574597) for the MACE reduction,
   STEP 1 for responder share — and published incidence for baseline rates. A row without a
   citation does not go in.
3. Wire the cost offset into M5's `offset` per therapy, so it reaches M7 through the therapy cost
   and not as a line added at the end.
4. The outcomes panel: responders, events avoided and cost avoided per year, each figure naming
   its trial inline.

**What bites here.** The offset must average across the horizon rather than take year 1 — M5
carries one offset figure and the effect decays, so year 1 would credit the therapy with its best
year every year. Exposure is persistence-adjusted, not headline uptake. A therapy with no supplied
effect raises `NO_OUTCOME_EVIDENCE`; it does not return zero, because zero avoided events and no
evidence about avoided events are different claims and a payer will ask which one this is.

**Done when.** A scenario states what the spend buys, every effect traces to a named trial, and
adding an effect reduces M7's incremental impact by exactly the offset it produces — asserted in a
golden test, not observed by eye.

---

## Phase 13 — Disease Subgroups

**Read.** `docs/modules/M18-disease-subgroups.md`; ARCHITECTURE.md §4B, §6.3; `docs/modules/M3-eligibility-segmentation.md` §12, whose deferred segmentation this is.

**Build.**

1. `Subgroup` enum, `SUBGROUP_PRIORITY`, and `biet_engine/subgroups.py` with `allocate_shares`
   and `aggregate_segments`. Both pure.
2. `disease_subgroups` and `subgroup_prevalence` tables, seeded per market with the tier each
   figure actually earns — B where a national survey supports it, C where it is a regional
   analogue, and no A without a country-specific published figure.
3. The service-layer loop: resolve inputs per subgroup, call the existing engine once per segment,
   aggregate. **No engine signature changes.** If you find yourself editing `compute_funnel`'s
   parameters, stop and re-read §4 of the spec — a subgroup is a scenario dimension, and that is
   the whole reason `biet_engine` can stay pure.
4. Scenario payload gains `subgroups`; the calculation response gains `segments` alongside the
   existing totals, so a client that ignores subgroups still reads a correct total.
5. The `features/subgroups/` slice: selector, share allocator with a live residual, breakdown
   table, contribution chart.

**What bites here.**

- **Double counting.** A patient with obesity, T2D and hypertension appears in all three
  prevalence statistics. The five adult subgroups partition the population by
  `SUBGROUP_PRIORITY`, `OBESITY_ALONE` is the derived residual and cannot be supplied, and
  paediatric obesity is disjoint with its own denominator and does not enter that sum.
- **Averaging ratios.** Cost per treated patient, PMPM and every rate are recomputed from
  aggregated numerator and denominator. Segments differ in size by more than an order of
  magnitude, so a mean of segment ratios is not approximately right — it is wrong by roughly the
  size ratio.
- **The paediatric definition.** Obesity in children is the 95th BMI centile for age and sex, not
  the adult BMI ≥ 30 cut-off. Applying the adult threshold to a twelve-year-old selects a much
  smaller and sicker group than the label suggests, and the interface must say which is meant.
- **The comparator mix per segment.** A patient with obesity and T2D is already on
  glucose-lowering therapy; a patient with obesity alone is on a lifestyle programme or nothing.
  One mix across both understates displaced cost in the first and overstates it in the second,
  and those errors do not cancel.

**Done when.** Splitting a population into five segments that all carry the disease defaults
reproduces the undifferentiated total **exactly** — this is the golden test that catches every
aggregation error this design is exposed to. Then: moving share from `OBESITY_ALONE` to
`OBESITY_ESTABLISHED_CVD` increases avoided events and the offset, and a segment with no outcome
evidence contributes cost and no events with the aggregate naming it.

---

## Phase 14 — Payer Perspective and Decision Views

**Read.** `docs/modules/M17-payer-perspective.md`; ARCHITECTURE.md §5.7, §5.8; `docs/modules/M8-affordability-solver.md`.

**Build.**

1. `PayerPerspective`, `CoveredPopulation`, `PerspectiveConfig`, and `covered_populations` seeded
   for the government and health-system perspectives only. Insurer and employer are properties of
   a client, not of a country: an empty row is correct there and a placeholder is not.
2. The funnel runs on covered lives. Do **not** compute a national result and scale it down —
   that carries the national comorbidity mix, comparator mix and access rate into a population
   that has none of them.
3. PMPM and PMPY, per year and cumulative. Four decimal places minimum, sign convention on the
   figure, recomputed from totals across markets and subgroups rather than averaged.
4. Break-even price: call M8's solver with a zero-impact target. Do not reimplement the search.
   Return all four `BreakEvenStatus` outcomes distinctly — `ALREADY_COST_SAVING` reports headroom,
   `UNREACHABLE` says the price is not the lever.
5. Low, base and high uptake as three complete engine runs. Not a scaled result: persistence
   weighting, the averaged outcome offset, incumbent rescaling and any non-proportional
   displacement matrix are all non-linear in uptake.
6. `features/payer-view/` slice, and `decision_view` in the forward calculation response when a
   perspective is set — a payer reading a result should not have to ask for the payer view.

**What bites here.** `include_indirect_costs` is valid only for the employer perspective and is
rejected elsewhere rather than ignored; a productivity gain is real and is not a line in an
insurer's budget. `cumulative_pmpm` divides by total months in the horizon, not the sum of annual
PMPMs. Covered lives above the national population is a rejection, not a warning.

**Done when.** The base band reproduces the plain forward calculation exactly, a solved
break-even price re-run through the forward model yields cumulative impact of zero within
tolerance, and a two-market PMPM test asserts the recomputed figure rather than the averaged one.

---

## Phase 15 — Live Reference Data and Market Automation

**Read.** `docs/modules/M20-live-reference-data.md`; ARCHITECTURE.md §6.1, §6.2, §7.1–§7.4.

**Build.**

1. `FreshnessPolicy` per source with the cadence and max age in the spec's table, and
   `source_status`, `refresh_runs` and `material_moves` tables.
2. `POST /reference/refresh` and `/reference/refresh/{source}`, serialised per source. A scheduled
   worker at each source's cadence.
3. Publish-and-supersede semantics on every reference table. A refresh never updates a row in
   place, because a completed run must still resolve to what it was computed from.
4. Staging retention and pruning, with the raw payload moved out of the database to a
   hash-addressed file and staging rows referenced by a run inside the window protected from the
   prune.
5. Currency bound to the market. Calculation in the market's own currency, display conversion
   only, through the run's snapshotted FX set.
6. `GET /reference/markets/{iso3}` returning every pre-filled funnel input for a market with its
   provenance in one call, and the `ProvenanceBadge` / `StalenessChip` / `DataHealthPanel`
   components.

**What bites here.**

- **Fetch age and vintage are different numbers and both are reported.** WHO's diabetes indicator
  fetched this morning is still a 2014 figure. A tool that conflates them claims to be current
  while serving a decade-old value.
- **A partial refresh is worse than none.** Validation failure aborts before publish and leaves
  prior values in force; one indicator moving while a related one does not produces an
  internally inconsistent market.
- **No hard-coded fallback, anywhere.** A source outage serves the last published value and names
  its age. A wrong number that never expires is worse than a stale one that announces itself.
- **Large moves publish and flag.** Suppressing a move makes the tool quietly wrong; absorbing it
  silently lets a source's unit change pass as an epidemiological shift.

**Done when.** Selecting a market fills the model with labelled current values; a run completed
before a refresh still resolves to its snapshot after it; and the CI row-count assertion on the
published reference set passes.

---

## Phase 16 — Workbook Import and Dynamic Inputs

**Read.** `docs/modules/M19-workbook-import.md`; `backend/src/biet_api/services/excel_service.py`, whose export this must round-trip against.

**Build.**

1. The eight input sheets of §5.1, and the template endpoint that hands the analyst an empty
   conforming workbook before they upload anything.
2. One parser for both the scenario workbook and the comparator-only workbook. The comparator
   sheet uploaded alone replaces the comparator set and touches nothing else.
3. Cell-level validation producing `ImportFinding`s with sheet and cell references, then
   validation through the **same Pydantic request models the API accepts**. Do not maintain a
   parallel notion of a valid scenario; two sets of rules diverge, and the divergence shows up as
   a file that imports and then fails to calculate.
4. Provenance per imported value: `workbook:<filename>`, `<Sheet>!<Cell>`, tier D unless the row
   fills its `Source` and `Tier` columns.
5. Registry matching for drug names, returning ranked candidates for unmatched names and offering
   M12's promotion path. Import never writes to the registry directly.
6. `RegistryCombobox` — the shared editable-dropdown control — and the editable comparator grid
   with a live share total.
7. Add the input sheets to the export so the round trip closes.

**What bites here.**

- **Rate units.** A percentage read as a fraction and a fraction read as a percentage are both
  catastrophic and both look plausible in a log. Every rate column header declares its unit,
  the boundary converts exactly once, and a value outside its declared range is
  `AMBIGUOUS_RATE_UNIT` — never coerced.
- **All findings in one pass, and whole-file rejection.** An analyst fixing a fifty-row sheet
  should get fifty messages once. A parser that stops at the first error turns one correction
  into fifty round trips.
- **Currency on every money column.** No implicit currency, ever.
- **Values, not formulas.** `data_only=True`, and a workbook saved without cached values is
  rejected with that reason named rather than silently read as empty.

**Done when.** Export → import → export produces a byte-identical input section, a ten-error file
returns ten findings and creates nothing, and an imported scenario calculates with its provenance
intact.

---

## Phase 17 — Guided Analyst Interface

**Read.** `docs/modules/M21-analyst-interface.md`; ARCHITECTURE.md §11; `backend/src/biet_api/constants/parameter_paths.py`, which is the vocabulary the glossary is keyed on.

**Build.**

1. `field_glossary` and `error_messages` as seed data under version control — they are part of
   the product's argument and are reviewed like code.
2. `GET /glossary` and `GET /scenarios/{id}/fields`, the second returning value, provenance,
   freshness and override state together so the interface never has to pair them itself.
3. The nine stages of §5.1 with completeness state and free navigation. A wizard that forbids
   going back is a wizard nobody finishes.
4. `FieldRow` — every input in the application is one — and `TwoWorldCard`, the only way a
   headline figure is rendered.
5. The eight default result cards, everything else in the detail accordion in the §5.4 order.
6. Analyst-facing messages for every error code, naming the field to change.
7. The two build-time tests: every rendered `parameter_path` has a glossary entry, and every error
   code has a message. Both are set comparisons, and both fail the build.

**What bites here.**

- **`TwoWorldFigure` is a type, not a convention.** It cannot be constructed with one world, which
  is what stops a headline drifting into the gross cost of the new therapy. Non-negotiable 2 is
  exactly what an interface erodes first.
- **The build-time glossary test carries this module.** Documentation drifts from an interface
  within one release unless something mechanical fails when it does.
- **Hover is not enough on its own.** Explanation opens on keyboard focus and is announced to a
  screen reader; a tooltip only a mouse can open is not an explanation for everyone.
- **Formatting is market-aware.** Lakh and crore are right for an Indian payer and wrong for a
  German one. This is the one place locale belongs.

**Done when.** A first-time user selects a market, types nothing, and reaches eight populated
cards each of which shows without, with, and the difference on hover — and all nine stages pass
axe at WCAG 2.1 AA.

---

## Phase 18 — Language Model Gateway

**Read.** `docs/modules/M22-llm-gateway.md`; ARCHITECTURE.md §12; `backend/src/biet_api/services/narrative_service.py`, whose `_draft_with_model` this generalises; `backend/src/biet_engine/narrative.py::validate_numbers`, which stays where it is.

**Build.**

1. `LlmGateway` over the OpenAI-compatible chat completions surface, with `ProviderConfig` for
   Alibaba Model Studio (Qwen, international endpoint), ModelScope, Hugging Face and the existing
   Anthropic path.
2. Configuration from the environment only. `.env.example` gains commented placeholders and no
   values. `ProviderConfig` names the variable holding the key and never holds the key.
3. Every response validated against `LlmRequest.numeric_context` before return. A narrative
   request with an empty context is rejected before any call is made.
4. Ordered failover, a circuit breaker after three consecutive failures with a cooldown, and a
   persisted per-provider per-model daily counter checked **before** the call rather than
   discovered at the 429.
5. Narrative cached on `(run_id, section, provider, model, prompt_hash)`; `no_external_llm` on a
   scenario forcing the deterministic path and recorded on the run.
6. `GET /ai/providers` reporting configured, reachable and remaining — never a key.

**What bites here.**

- **A fabricated figure does not fail over.** A second model is no more entitled to invent a
  number than the first, and retrying until something passes the validator is precisely the wrong
  instinct. It falls straight through to deterministic text.
- **No test calls a live provider.** A suite that needs free-tier quota to pass fails on the day
  the quota runs out, which is the day before the demo. Record transcripts.
- **The quota counter persists.** An in-memory counter that forgets on redeploy burns a free tier
  in an afternoon.
- **Verify the free tiers yourself.** The figures in the spec's registry table are as reported in
  the review of 2026-08-25 and are not verified by this project. Providers change terms; check
  the provider's own documentation when you configure it. Note also that ModelScope's free
  inference requires a linked Alibaba Cloud account with real-name verification, and that the
  mainland and international Model Studio endpoints do not accept each other's keys — both are
  better discovered now than during a demo.

**Done when.** The provider switches by environment variable with no code change, a fabricated
figure never reaches a deliverable, no credential appears in a log line, error or response — the
test asserts this against a fixture key — and the tool produces its full output with no provider
configured at all.

---

## Writing a new phase prompt

Match the shape: **Read** names the specs, **Build** is a numbered list of deliverables,
**What bites here** is the two or three things that will actually go wrong, and **Done when** is
observable — a test that passes, not a feeling that the work is finished.

The "what bites" section is the one worth spending time on. Anyone can restate a specification;
the value is in naming the error this particular module invites, before someone makes it.
