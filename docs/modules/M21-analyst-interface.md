# M21 — Guided Analyst Interface

Module specification v1.0 · Owner area: Frontend + Backend · Depends on: M17, M18, M19, M20

---

## 1. Purpose

Make the tool usable by an HEOR manager who has never seen it, by ordering the work from inputs
to outputs and making every number on screen explain itself.

The primary user is not a modeller. They are a health economics and market access manager who
needs a defensible number for a payer conversation this week, and who will judge the tool by
whether they can tell what it is asking for and what it has told them. Correct arithmetic that
nobody can read is not a deliverable.

## 2. Scope

**In scope.** The stage order and what each stage asks for; the field glossary and where it
lives; hover and inline explanation for every input and every output; the with-and-without
framing of every result; progressive disclosure; error messages in the analyst's language;
accessibility and the mechanical tests that keep all of it from rotting.

**Out of scope.** New calculation. This module renders what M2–M20 produce and adds no number of
its own — a figure that appears only in the interface has no provenance and cannot be exported.
Visual identity and brand. Mobile layout: this is a desktop analysis tool.

## 3. Dependencies

**Upstream.** M20 for pre-filled values and their freshness; M17 for the payer-facing figures;
M18 for the segment breakdown; M19 for import and the combobox contract; M10 for narrative and
export, which consume the same glossary.

**Downstream.** None. This is the surface.

## 4. Contracts

The glossary is served by the backend, not written into the frontend. One definition then feeds
the interface, the PDF, the PowerPoint and the exported workbook, and the four cannot disagree.

```python
class FieldKind(StrEnum):
    INPUT = "input"
    OUTPUT = "output"
    DERIVED = "derived"


class FieldExplanation(BaseModel):
    """One entry in the glossary, keyed by the parameter path that already exists."""

    model_config = ConfigDict(frozen=True)

    parameter_path: str              # constants/parameter_paths.py is the vocabulary
    kind: FieldKind
    label: str                       # "Diagnosis rate"
    plain_language: str              # one sentence, no jargon, no acronym undefined
    unit: UnitKind                   # PERCENT | MONEY | COUNT | YEARS | RATIO
    why_it_matters: str              # what moves in the answer when this moves
    affects: tuple[str, ...]         # parameter paths downstream of this one
    typical_range: str | None = None
    common_error: str | None = None  # the mistake analysts actually make here


class ResolvedField(BaseModel):
    """What the interface renders for one field: the value, its basis, and its explanation."""

    model_config = ConfigDict(frozen=True)

    explanation: FieldExplanation
    value: float | str | None
    provenance: Provenance | None
    freshness: FreshnessState | None
    overridden: bool
    original_value: float | str | None = None


class TwoWorldFigure(BaseModel):
    """Every headline output. Never a single number on its own."""

    model_config = ConfigDict(frozen=True)

    label: str
    without_intervention: Money | float
    with_intervention: Money | float
    difference: Money | float
    plain_language: str
    unit: UnitKind
```

`TwoWorldFigure` is a type rather than a convention because non-negotiable 2 — budget impact is
incremental, never the gross cost of the new therapy — is exactly the thing an interface erodes
first. A headline card that cannot be constructed without both worlds cannot drift into showing
one.

## 5. Logic specification

### 5.1 The flow is inputs, then outputs, in the order the model works

Nine stages, left to right, each with one job. The order is the review's first ask and it is
also the order the calculation actually runs in, which is what makes it teachable.

| # | Stage | Asks for | Module |
|---|---|---|---|
| 1 | Setup | Disease, markets, perspective, covered lives, launch year, horizon | M1, M17 |
| 2 | Population | Population, growth, prevalence, diagnosed share, subgroup mix | M2, M18, M20 |
| 3 | Eligibility | BMI threshold, comorbidity requirements, treatment eligibility | M3 |
| 4 | Current care | The comparator mix — medicines, lifestyle programme, bariatric surgery | M5, M12 |
| 5 | New intervention | Product, regimen, price, administration and monitoring cost | M5 |
| 6 | Uptake | Year-by-year adoption, and the low and high bands | M4, M17 |
| 7 | Treatment behaviour | Adherence, discontinuation, persistence, weight regain | M6, M16 |
| 8 | Outcomes | Response rate, risk reductions, event costs, each with its trial | M16 |
| 9 | Results | Everything below | M7–M9, M17 |

Every stage carries a completeness state — **resolved** (a published value is in force),
**overridden** (the analyst changed it), **missing** (nothing resolved and nothing supplied) —
and the analyst can move forward with anything resolved. Because M20 §5.7 pre-fills the model,
a first-time user reaches stage 9 without typing anything and sees a complete, provenanced,
defensible base case for their market. That first run is the demonstration; everything after it
is refinement.

Stages are navigable in any order. A wizard that forbids going back is a wizard nobody finishes.

### 5.2 Every input explains itself

Hovering or focusing any input shows four things, in this order:

1. **What it is**, in one sentence with no jargon. "The share of people with obesity whose
   condition has been diagnosed and recorded by a clinician."
2. **The value in force**, and its unit.
3. **Where it came from** — source, vintage year, confidence tier, resolution level, and how
   long since the tool last checked. A tier C seeded default says so, in those words: "Seeded
   default, not country-specific — replace it if you have a local figure."
4. **What it changes** — the downstream figures this input moves.

Where the field has a `common_error`, it is shown. The prevalence field says that WHO publishes
20.6% and the model stores 0.206, and that both readings appear in spreadsheets.

An overridden field shows the original beside the override, and the two are never conflated.

### 5.3 Every output explains itself, and states both worlds

Hovering any result shows what the number means in one sentence, and the two worlds it came
from. This is the review's request rendered literally:

```
Incremental budget impact, Year 3
  Without this intervention      €41.2 M     what the payer spends on current care
  With this intervention         €47.9 M     current care displaced, plus the new therapy
  Difference                     +€6.7 M     added cost to the payer
```

Rules that hold everywhere in the results view:

- **No headline figure appears without its two worlds.** The gross annual cost of the new
  therapy is not a headline; it is a component, and it lives in the cost bridge where it means
  something.
- **The sign convention is on the figure, not in a footnote.** Positive is added cost.
- **Per-member figures state their denominator inline.** "€0.0043 per member per month, across
  4,000,000 covered lives."
- **Every figure carries the weakest confidence tier of the inputs that produced it.** A result
  built on a tier D placeholder is labelled tier D however elegant the arithmetic was.
- **Events avoided name their trial on the figure**, per M16 §5.6.

### 5.4 The default view is eight numbers

The results stage opens on the figures the review asked for, and nothing else:

| Card | Figure |
|---|---|
| 1 | Total cost of current care, over the horizon |
| 2 | Total cost with the intervention |
| 3 | Incremental budget impact, cumulative |
| 4 | Incremental budget impact by year — the chart |
| 5 | Patients treated, per year |
| 6 | Cost per treated patient |
| 7 | PMPM impact |
| 8 | Break-even price |

Below the fold, in this order: events avoided and costs avoided (M16), the low–base–high band
(M17), the subgroup breakdown (M18), the cost bridge (M13), the tornado and PSA (M9), the
evidence-priority list (M15), and the assumption register. Each is one click, none is hidden,
and the tornado does not greet a market access manager on arrival.

### 5.5 Plain language rules

- No acronym appears undefined on first use. PMPM is "per member per month (PMPM)" the first
  time it appears on a view, and PMPM after.
- "Incremental budget impact" carries "the difference between what the payer spends with and
  without the new therapy" wherever it is a headline.
- Percentages are displayed as percentages and stored as fractions — non-negotiable 5, and the
  formatter is the only place the multiplication happens.
- Money always shows its currency code, and a converted figure names the FX date (M20 §5.6).
- Years display as both launch-relative and calendar — "Year 3 (2030)" — since non-negotiable 7
  makes the first canonical and a payer thinks in the second.
- Large numbers use the market's own convention. An Indian result reading in lakh and crore is
  right for an Indian payer and wrong for a German one; the formatter is market-aware, and this
  is the one place where locale belongs.

### 5.6 Errors speak to the analyst, not about the code

Every engine and validation error maps to a message naming what to change and where. The mapping
lives beside the glossary, keyed by error code, and an unmapped code is a test failure.

| Raised | Shown |
|---|---|
| `FunnelInvariantError` | "These eligibility criteria would qualify more patients than have been diagnosed. Check the BMI threshold in Eligibility." |
| `CurrencyMismatchError` | "This comparator is priced in USD and the German market calculates in EUR. Set a EUR price, or change the market." |
| `CorrelatedCriteriaError` | "BMI ≥ 30 and BMI ≥ 35 overlap. Applying both counts the same restriction twice — choose one." |
| `NO_OUTCOME_EVIDENCE` | "No trial evidence has been supplied for this therapy, so no avoided events are claimed. This is not the same as zero." |
| `STALE_REFERENCE` | "WHO diabetes prevalence is a 2014 figure — the most recent this indicator publishes. It is projected forward, and the projection is stated in the assumptions." |
| `SHARES_DO_NOT_SUM` | "Market shares total 94%. They must total 100% — 6% of patients are currently unaccounted for." |

### 5.7 Nothing starts blank, and every list is editable

Consequences of M20 §5.7 and M19 §5.7, restated as interface rules because this is where they
are visible:

- Selecting a market fills the population stage. The analyst edits; they do not transcribe.
- Every dropdown backed by reference data accepts a value that is not in it, through
  `RegistryCombobox`, and a typed value is labelled as the analyst's own.
- The comparator table is an editable grid with add and remove, and it imports from a
  spreadsheet — the Streamlit prototype's most-used surface, and the one the review named twice.
- A share total that does not reach 100% is shown live as a running total, not discovered on
  submission.

### 5.8 Recalculation, and what the analyst sees while waiting

Debounced at 250 ms per ARCHITECTURE.md §11.4, previous result retained while in flight, request
cancelled on supersession. The in-flight result is visibly marked as superseded rather than
blanked — a screen that empties on every keystroke reads as broken, and the 200 ms budget on
`/calculate` exists to make this feel immediate.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| A rendered field has no glossary entry | Build fails (§10). It never reaches a user |
| An error code has no analyst-facing message | Build fails |
| A headline figure lacks one of its two worlds | Type error — `TwoWorldFigure` cannot be constructed |
| A value is missing and has no resolved default | Stage marked incomplete, naming the field; the run is still permitted if the engine can proceed |
| A market is selected with no reference data | The market is offered as unavailable with the reason, not silently absent |
| A tier D input feeds a headline | The headline is labelled tier D |
| Text is truncated for layout | Full text remains available on hover; never truncated in export |
| The user's locale differs from the market's | Market convention governs money; user locale governs dates |

## 7. Data requirements

Creates `field_glossary`: parameter path, kind, label, plain language, unit, why it matters,
affects, typical range, common error. Keyed on the vocabulary already defined in
`biet_api/constants/parameter_paths.py`, which makes the coverage test in §10 a set comparison
rather than a judgement call.

Creates `error_messages`: code, analyst-facing message, the stage to send them to.

Both are seed data under version control, not user-editable content. They are part of the
product's argument and they are reviewed like code.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/glossary` | The whole glossary; cached aggressively, it changes with releases |
| GET | `/api/v1/glossary/{parameter_path}` | One entry |
| GET | `/api/v1/scenarios/{id}/fields` | `ResolvedField` per path — value, provenance, freshness, override state |

`/scenarios/{id}/fields` is what lets the interface render explanation and value together
without assembling them from separate calls and losing the pairing.

## 9. Frontend

Slice `features/guided-flow/`, plus shared components every slice uses.

- `StageNav` — the nine stages, each showing its completeness state
- `FieldRow` — label, control, value, `ProvenanceBadge`, `StalenessChip`, explanation on hover
  and on focus. Every input in the application is one of these
- `TwoWorldCard` — the only way a headline figure is rendered
- `ResultsSummary` — the eight cards of §5.4
- `DetailAccordion` — everything below the fold, in the §5.4 order
- `ErrorBanner` — analyst-facing message, with a link to the stage and field that caused it

Hover content is also reachable by keyboard focus and is announced to a screen reader. A
tooltip that only a mouse can open is not an explanation for everyone.

## 10. Test specification

| Class | Test |
|---|---|
| Build | every `parameter_path` a view renders has a `field_glossary` entry — set difference must be empty |
| Build | every error code the API can return has an `error_messages` entry |
| Unit | `TwoWorldFigure` cannot be constructed without both worlds |
| Unit | the percent formatter multiplies exactly once; a fraction never renders as a fraction |
| Unit | money renders with its currency code; a converted figure renders with the FX date |
| Unit | an overridden field renders both values |
| Unit | a tier D input propagates a tier D label to the headline it feeds |
| Unit | Indian formatting produces lakh and crore; German produces neither |
| Component | hover content opens on keyboard focus and carries an accessible name |
| Component | the in-flight state marks the previous result superseded rather than clearing it |
| E2E | select a market, change nothing, reach the results stage with eight populated cards |
| E2E | every card's hover shows without, with, and the difference |
| E2E | import a comparator workbook and see the mix change in the results without a reload |
| A11y | axe passes on all nine stages at WCAG 2.1 AA |

The two build-time tests carry the module. Documentation drifts from an interface within one
release unless something mechanical fails when it does, and a glossary keyed on the same
vocabulary the override system already uses makes that check a set comparison.

## 11. Acceptance criteria

- [ ] Nine stages, ordered inputs to outputs, each with a completeness state
- [ ] A first-time user reaches a complete base case for their market without typing
- [ ] Every input explains what it is, its value, its provenance and what it changes
- [ ] Every headline output shows without, with, and the difference
- [ ] No gross-cost figure is presented as a headline
- [ ] The default results view is eight cards; everything else is one click away
- [ ] Every error appears in the analyst's language, naming the field to change
- [ ] The glossary is served from the backend and shared with every export
- [ ] A rendered field without a glossary entry fails the build
- [ ] All nine stages pass WCAG 2.1 AA

## 12. Assumptions & open questions

**Assumptions.** Desktop, English, one analyst at a time on a scenario. The glossary can be
written once and maintained with the model — true while there is one disease, and the thing most
likely to strain when there is a second. Pre-filled defaults are a help rather than a hazard,
because every one is labelled with its tier; that assumption fails the moment a tier C default
renders identically to a tier A published figure, which is why §5.2 and §5.3 insist it does not.

**Open questions.**
1. Whether the nine stages should be one scrolling page rather than steps. A single page is
   faster for a returning user and overwhelming for a new one; the stage model with free
   navigation is the compromise, and it is worth testing against a real user before it is fixed.
2. Whether to offer a "explain this result" action that composes the narrative for one figure
   through M10, rather than only for the run as a whole.
3. Whether the market-aware number formatting should extend to the exported workbook, where a
   crore-formatted cell is harder to use in downstream Excel arithmetic than a plain number.
