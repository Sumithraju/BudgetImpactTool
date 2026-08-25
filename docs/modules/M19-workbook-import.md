# M19 — Workbook Import and Dynamic Inputs

Module specification v1.0 · Owner area: Backend · Depends on: M1, M5, M12, M18

---

## 1. Purpose

Accept a company's own inputs, market data and comparator set as a spreadsheet, and make every
input in the tool editable against a live registry rather than fixed to a seeded list.

HEOR runs on Excel. A tool that requires re-typing a market model someone has already built does
not fit the workflow it is meant to serve, and an analyst who cannot add the comparator their
market actually uses will stop at the first screen. Import accepts a scenario workbook and a
comparator workbook, validates every cell against the same rules the API enforces, and rejects
the file with a sheet-and-cell reference rather than importing something half-right.

## 2. Scope

**In scope.** The workbook contract — sheets, columns, units, currencies; cell-level validation
and error reporting; provenance for every imported value; matching imported drug names against
the M12 registry; the round trip between export and import; the registry-backed editable
dropdown contract that the same rules govern.

**Out of scope.** Reading arbitrary spreadsheets. The importer accepts a defined workbook, and
the tool supplies a template that already conforms; guessing the meaning of an unlabelled column
is how silent errors enter a model. CSV: a budget impact model has multiple related tables and a
flat file loses the relationships. Formula evaluation — values are read, not recomputed;
`data_only=True`, and a workbook saved without cached values is rejected with that reason named.

## 3. Dependencies

**Upstream.** M1 for the scenario shape being populated; M12 for the comparator registry that
imported names resolve against; M18 for the subgroup a population row belongs to; M5 for the
cost fields.

**Downstream.** Everything. An imported scenario is a scenario, and once validated it is
indistinguishable from one built in the interface except in its provenance, which says where
each value came from.

## 4. Contracts

```python
class WorkbookKind(StrEnum):
    SCENARIO = "scenario"
    COMPARATORS = "comparators"


class CellRef(BaseModel):
    """Every finding points here. A message without one is not actionable."""

    model_config = ConfigDict(frozen=True)

    sheet: str
    cell: str                        # "C7"
    column_label: str | None = None


class ImportFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    severity: FindingSeverity        # ERROR | WARNING
    code: str                        # MISSING_COLUMN | AMBIGUOUS_RATE_UNIT | ...
    message: str                     # in the analyst's language, not the parser's
    ref: CellRef | None = None
    supplied: str | None = None
    expected: str | None = None


class ImportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: WorkbookKind
    accepted: bool
    findings: tuple[ImportFinding, ...]
    scenario: ScenarioDraft | None = None
    unmatched_drugs: tuple[UnmatchedDrug, ...] = ()
    rows_read: int = 0


class UnmatchedDrug(BaseModel):
    model_config = ConfigDict(frozen=True)

    supplied_name: str
    ref: CellRef
    candidates: tuple[RegistryCandidate, ...]     # ranked, may be empty
```

## 5. Logic specification

### 5.1 The workbook contract

One workbook, one scenario. Sheets, and what each carries:

| Sheet | Shape | Contents |
|---|---|---|
| `Scenario` | key/value | Asset name, disease, markets, launch year, horizon, perspective, covered lives, currency |
| `Population` | one row per market × subgroup | Covered or national population, prevalence, diagnosis rate, treatment rate, access rate |
| `Eligibility` | one row per criterion | Criterion, subgroup, factor, enabled, source |
| `Comparators` | one row per therapy × market | Name, type, market share, drug cost, administration, monitoring, adverse-event cost |
| `NewIntervention` | key/value | Name, route, dose, frequency, unit price, administration cost, monitoring cost |
| `Uptake` | one row per year | Year, low, base, high |
| `Behaviour` | key/value | Adherence, discontinuation, 12-month persistence, weight regain per year |
| `Outcomes` | one row per effect | Subgroup, event class, baseline rate, relative reduction, unit cost, trial, follow-up |

The `Comparators` sheet is also the standalone comparator workbook: uploaded alone, it replaces
the comparator set of an existing scenario and nothing else. That is the review's separate ask,
and it is the same parser with the same rules, not a second implementation.

Every sheet's header row is fixed and matched by label, not by position — a user who inserts a
column should not silently shift every value one place. A missing required column is an error
naming the column; an unrecognised extra column is a warning naming it, and is ignored.

### 5.2 Units are declared, never inferred

The single most expensive class of error in a spreadsheet-driven model is a rate that is a
percentage in one place and a fraction in another. Non-negotiable 5 says rates are fractions
internally and only presentation multiplies by 100, so the boundary is here and it converts
exactly once.

- Every rate column header states its unit explicitly: `Prevalence (%)` or `Prevalence (0–1)`.
- A value in a `(%)` column above 100, or in a `(0–1)` column above 1, is an error —
  `AMBIGUOUS_RATE_UNIT` — naming the cell and both readings. It is never coerced. A prevalence
  of 20.64 silently read as 2064% and a prevalence of 0.2064 read as 0.2% are both catastrophic
  and both look plausible in a log.
- Every money column header carries its ISO 4217 code, or the sheet inherits the `Scenario`
  sheet's currency and the header says which. A money column with neither is an error.
  Non-negotiable 6: money carries a currency code, and an import is not an exception.
- Years are launch-relative in the model and calendar in the sheet. The `Uptake` sheet is
  labelled `Year 1 … Year N` relative to launch, and the `Scenario` sheet's launch year is what
  converts them. A sheet using calendar years is accepted only if the launch year is present and
  the first year matches it.

### 5.3 Validation is the API's, not a second set of rules

The importer builds the same Pydantic request models the API accepts and validates through them.
It does not maintain a parallel notion of what a valid scenario is — two sets of rules diverge,
and the divergence surfaces as a file that imports and then fails to calculate.

Cell-level checks that precede model validation, because a type error needs a cell reference to
be actionable:

| Check | Finding |
|---|---|
| Required sheet absent | `MISSING_SHEET`, naming it and listing the sheets found |
| Required column absent | `MISSING_COLUMN`, with the sheet |
| Non-numeric value in a numeric column | `NOT_A_NUMBER`, with the cell and what was there |
| Blank required cell | `MISSING_VALUE`, with the cell |
| Rate outside its declared unit's range | `AMBIGUOUS_RATE_UNIT` |
| Market share total off 1.0 by > 0.5 pp | `SHARES_DO_NOT_SUM`, with the total found |
| Market share total off by ≤ 0.5 pp | Warning; normalised, and the normalisation is reported |
| Unknown ISO3 market code | `UNKNOWN_MARKET`, listing the ten supported |
| Currency code not ISO 4217 | `UNKNOWN_CURRENCY` |
| Formula cell with no cached value | `NO_CACHED_VALUE`, telling the user to re-save from Excel |

### 5.4 A file is accepted whole or not at all

Any `ERROR`-severity finding rejects the workbook. Nothing is written, no partial scenario is
created, and every finding is returned at once — not the first one. An analyst fixing a
fifty-row sheet should get fifty messages in one pass, and a parser that stops at the first
error turns one correction into fifty round trips.

Warnings do not reject. They travel onto the created scenario and appear beside the values they
concern, so a normalised share total is visible in the result and not only in the import log.

### 5.5 Provenance for an imported value

Every imported value carries:

```
source           = "workbook:<original filename>"
note             = "<Sheet>!<Cell>"
confidence_tier  = from the row's Source/Tier columns if present, else D
resolution_level = SCENARIO_OVERRIDE
```

Tier D by default is the honest answer and an important one: a number typed into a spreadsheet
has no published basis until someone states one. The sheets therefore carry optional `Source`
and `Tier` columns, and a row that fills them earns its tier. M15 then ranks an unsourced
high-swing import exactly as it should — as the first thing to go and find out.

### 5.6 Matching a drug name to the registry

An imported comparator name is matched against `comparator_assets` by exact name, then by
normalised name (case, punctuation, salt forms), then by brand-to-molecule alias. A match binds
to the registry row and inherits its curated fields.

An unmatched name is **not** silently created as a new drug. It is returned in
`unmatched_drugs` with ranked candidates, and the analyst either picks a candidate or promotes
the name into the registry through M12's existing intake path — which requires a regimen and a
price with a source, as it should. A comparator that appears in a market mix without those is a
number with no basis.

Import is not permitted to bypass M12's promotion rules. The registry is the single record of
what a drug is; letting a spreadsheet write to it directly would make it two.

### 5.7 The editable dropdown contract

The review's second ask is that inputs be dynamic — a dropdown whose options come from the
database but which accepts a value that is not in it. Every such control in the interface obeys
one contract, defined here because it is the same data rule as import:

- Options are fetched from the reference API, never hard-coded in the frontend.
- Free text is permitted where the field is a value rather than a closed set. Enums —
  perspective, event class, subgroup, price basis — are closed sets and are not free text.
  Non-negotiable 10: closed sets are enums.
- A free-text value creates a scenario-local override with the same provenance §5.5 gives an
  imported value: tier D, `SCENARIO_OVERRIDE`, sourced to the user.
- The control shows the resolved value, its source and its tier before the user changes
  anything, and shows both the original and the override afterwards.
- A free-text drug name follows §5.6 — it offers promotion, it does not create a registry row.

### 5.8 The round trip

The exported workbook of M10 gains the eight input sheets of §5.1, and the resulting file
re-imports to the identical scenario. This is the acceptance test that keeps the two contracts
honest: an export that cannot be re-imported means one side has drifted, and it will be
discovered by a user rather than by a test unless this is asserted.

Output sheets — `Summary`, `Assumptions`, `Funnel`, `By year`, `Narrative` — are ignored on
import. They are results, and re-importing a result as an input is how a model starts believing
its own output.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| File is not a workbook | Rejected, `NOT_A_WORKBOOK` |
| File exceeds the size limit | Rejected before parsing, naming the limit |
| Workbook is password protected | Rejected, `PROTECTED_WORKBOOK` |
| Sheet present but empty | `MISSING_VALUE` per required field, not a silent empty scenario |
| Duplicate rows for the same market and subgroup | Rejected, `DUPLICATE_ROW`, naming both cells |
| Merged cells in a data range | Rejected, naming the range — a merged cell has one value and several meanings |
| Comparator sheet uploaded alone | Replaces the comparator set only; other inputs untouched |
| Comparator sheet for a market not in the scenario | Warning, rows ignored, market named |
| Text in a numeric cell that Excel stored as text ("1,234") | `NOT_A_NUMBER` naming the cell; not coerced |
| Trailing blank rows | Ignored |
| More than one currency in one money column | Rejected, `MIXED_CURRENCY_COLUMN` |

## 7. Data requirements

No new reference tables. Creates `workbook_imports`: import id, scenario id, filename, SHA-256
of the uploaded bytes, kind, row count, findings, imported-by, imported-at. The hash is what
makes an imported run reproducible — it identifies the exact file, and a later dispute about a
number resolves against the file rather than against a memory of it.

The uploaded file itself is retained for the retention period configured for staging data under
M20 §5.1, then pruned. The hash and the findings outlive it.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/imports/template` | Returns the empty workbook, sheets and headers in place |
| POST | `/api/v1/imports/validate` | Multipart. Returns `ImportResult` and creates nothing |
| POST | `/api/v1/imports/scenario` | Multipart. Creates the scenario if accepted |
| POST | `/api/v1/scenarios/{id}/comparators/import` | Multipart. Replaces the comparator set |

`validate` before `scenario` is the intended flow and the interface uses it: an analyst sees
every finding and fixes the file before anything is created.

## 9. Frontend

Slice `features/workbook-import/`.

- `TemplateDownload` — offered before the upload control, because the first question is what
  shape the file should be
- `WorkbookDropzone` — validates on drop, imports on confirmation
- `FindingsTable` — severity, message, sheet and cell, sorted errors first, each row linking to
  the sheet and cell so the user can find it
- `UnmatchedDrugResolver` — supplied name, ranked candidates, and a promotion action
- `RegistryCombobox` — the shared control of §5.7, used by every dynamic field in the app

## 10. Test specification

| Class | Test |
|---|---|
| Unit | a valid workbook produces a scenario equal to the equivalent API payload |
| Unit | a missing required column names the column and the sheet |
| Unit | 20.64 in a `(0–1)` prevalence column raises `AMBIGUOUS_RATE_UNIT` and is not coerced |
| Unit | 0.2064 in a `(%)` column is accepted as 0.2064% — the unit is believed, not guessed |
| Unit | shares summing to 99.7% normalise and warn; 94% is rejected |
| Unit | every error in a file with ten errors is returned in one pass |
| Unit | one error anywhere means nothing is written |
| Unit | a money column with no currency is rejected |
| Unit | a formula cell with no cached value names the fix |
| Unit | an unmatched drug returns candidates and creates no registry row |
| Unit | imported values carry `workbook:<file>` and `<Sheet>!<Cell>` provenance |
| Unit | a text-formatted number is rejected rather than parsed |
| Golden | export → import → export produces a byte-identical input section |
| Integration | a comparator-only upload changes the mix and leaves the funnel untouched |
| Integration | an imported scenario calculates and its results carry the import's provenance |

## 11. Acceptance criteria

- [ ] A scenario workbook and a comparator workbook both import through one parser
- [ ] Every finding carries a sheet and cell reference
- [ ] All findings are returned in one pass, and any error rejects the whole file
- [ ] Rate units are declared per column and converted exactly once
- [ ] Every money value carries a currency code
- [ ] Imported values carry file-and-cell provenance and default to tier D
- [ ] Unmatched drug names offer promotion and never write to the registry directly
- [ ] Every dynamic field in the interface obeys the §5.7 combobox contract
- [ ] Exported workbook re-imports to the identical scenario

## 12. Assumptions & open questions

**Assumptions.** The analyst can be given a template — this is a tool with a first-run flow, not
a parser pointed at arbitrary files found in a share drive. Files are small enough to parse in
request scope; the size limit in §6 is what enforces that assumption rather than trusting it.

**Open questions.**
1. Whether to accept a partial workbook that carries only the sheets it wants to change,
   patching an existing scenario. It is convenient and it makes "what does this file mean on its
   own" unanswerable; currently only the comparator sheet has that privilege.
2. Whether the template should ship pre-populated with the resolved reference values for the
   selected markets, so the analyst edits rather than types. That is better for the user and it
   blurs which values came from the tool and which from them — resolvable only because §5.5
   records the origin per cell.
3. Whether an import should be allowed to set a tier above D from a `Tier` column without a
   `Source` column filled. Currently it is; requiring both is stricter and arguably right.
