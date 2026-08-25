# M20 — Live Reference Data and Market Automation

Module specification v1.0 · Owner area: Data + Backend · Depends on: M0, M2, M5

---

## 1. Purpose

Keep the database small and current, let the market choose its own currency, and make every
population input arrive already filled in.

The three are one concern. An analyst opening the tool for Germany should find the German
population, the German obesity prevalence and euros already in place, each labelled with where
it came from and how old it is — and should be told, rather than left to discover, when the
figure in front of them is out of date. What the tool stores locally exists to serve that, and
nothing more.

## 2. Scope

**In scope.** The freshness contract on every reference row; refresh on schedule and on demand;
what the database is allowed to retain and for how long; the market-to-currency binding and
where FX conversion happens; auto-resolution of every funnel input from published reference data
with its provenance; behaviour when a source is unreachable.

**Out of scope.** New sources — the register in ARCHITECTURE.md §7.1 stands, and this module
governs how what is already there stays current. Changing the resolution chain of §7.3. Live FX
lookup at calculation time, which non-negotiable 6 forbids outright.

## 3. Dependencies

**Upstream.** M0's ingestion pipeline, whose stages this module puts a policy around.

**Downstream.** M2 and M5 consume resolved values and are unchanged by this module — they
already accept a `Valued` with provenance. M17 reads covered lives through the same chain. M21
renders the freshness state this module produces.

## 4. Contracts

```python
class SourceId(StrEnum):
    WORLD_BANK = "world_bank"
    WHO_GHO = "who_gho"
    NADAC = "nadac"
    CURATED_PRICES = "curated_prices"
    OPENFDA = "openfda"
    CLINICALTRIALS = "clinicaltrials"
    FRANKFURTER_FX = "frankfurter_fx"


class FreshnessPolicy(BaseModel):
    """How old a value from this source may be before the tool says so."""

    model_config = ConfigDict(frozen=True)

    source: SourceId
    max_age_days: int
    refresh_cadence_days: int
    #: A published move larger than this is flagged for review rather than trusted.
    material_move_fraction: float = MATERIAL_MOVE_DEFAULT      # 0.20


class FreshnessState(StrEnum):
    CURRENT = "current"
    STALE = "stale"                  # older than max_age_days
    UNREACHABLE = "unreachable"      # last refresh failed; a prior value is in force
    NEVER_FETCHED = "never_fetched"


class SourceStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: SourceId
    state: FreshnessState
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    age_days: int | None
    rows_published: int
    message: str | None = None


class RefreshOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: SourceId
    started_at: datetime
    finished_at: datetime
    accepted: bool
    rows_staged: int
    rows_published: int
    material_moves: tuple[MaterialMove, ...]
    failure_reason: str | None = None


class MaterialMove(BaseModel):
    model_config = ConfigDict(frozen=True)

    table: str
    country_code: str
    parameter_path: str
    previous: float
    incoming: float
    change_fraction: float
```

## 5. Logic specification

### 5.1 The database holds what the model needs, and a bounded audit trail

Published reference tables are permanent and versioned — `countries`, `country_economics`,
`epidemiology`, `funnel_defaults`, `eligibility_criteria`, `drugs`, `drug_regimens`,
`drug_prices`, `fx_rates`, the adverse-event tables and the comparator registry. They are small:
ten markets, one disease, six subgroups and a bounded therapy set. Nothing about the calculation
requires more.

What must not grow without limit is the audit trail. `staging_extracts` preserves source payload
structure for traceability from a published value back to what the source actually returned, and
a weekly NADAC refresh over a 1.5-million-row extract will otherwise dominate the database
inside a month.

- Staging rows are retained for `STAGING_RETENTION_DAYS` (default 90) and pruned on a schedule.
- The raw extract is a file, addressed by SHA-256 and stored outside the database. Staging keeps
  the hash, the row count and the normalised projection, not the payload.
- Pruning never touches a staging row referenced by a `model_run` inside the retention window.
  Runs are immutable, and a run's trail must outlive the routine prune.

The test that keeps this honest is a size assertion in CI: total published reference rows for
the ten markets stay within a stated bound, and a change that multiplies them fails the build
with the count.

### 5.2 Every value states its age, and the tool says when it is stale

Each source has a `FreshnessPolicy` derived from its real cadence, not from a wish:

| Source | Refresh cadence | `max_age_days` | Note |
|---|---|---|---|
| Frankfurter FX | 1 | 7 | ECB publishes on working days |
| NADAC | 7 | 30 | Weekly file |
| openFDA | 7 | 90 | Contextual metadata only |
| ClinicalTrials.gov | 7 | 90 | Contextual metadata only |
| World Bank | 90 | 400 | Annual indicators; a year plus a month of slack |
| WHO GHO | 90 | 730 | Irregular. Diabetes has not moved since 2014 |
| Curated prices | manual | 180 | Human-maintained; staleness is a review prompt |

Two distinct ages exist and both are reported, because conflating them is how a tool claims to
be current while serving a decade-old number:

- **Fetch age** — how long since the tool last asked the source. Governed by the policy above.
- **Vintage** — the reference year of the datum itself. WHO's diabetes indicator is fetched
  today and is a 2014 vintage, and ARCHITECTURE.md §6.4 already requires that to be labelled.

A scenario built on a value past its policy's `max_age_days` carries `STALE_REFERENCE` naming
the source, the parameter and the age in days. It does not block the calculation. A payer
analysis is often the reason someone notices the data is old, and refusing to run would remove
the only signal.

### 5.3 A refresh publishes; it never mutates

Non-negotiable 9 makes runs immutable, and the reference data behind them has to behave
accordingly. A refresh follows the M0 pipeline — extract, validate, normalise, stage, transform,
publish — and publish is an insert that supersedes, never an update in place. Prior rows keep
their `valid_from`/`valid_to` and remain readable.

Consequences, all of them intended:

- A run completed yesterday still resolves to yesterday's values. Reopening it shows what it was
  computed from, not what the source says now.
- A new run picks up the new values, and the two runs differ. The interface shows both vintages
  when a scenario is re-run, so the change is visible rather than mysterious.
- A validation failure at any stage aborts before publish and leaves the prior values in force,
  with `SourceStatus.state = UNREACHABLE` and the failure reason recorded. Half a refresh is
  worse than none — one indicator moving while a related one does not produces an internally
  inconsistent market.

### 5.4 A large move is published and flagged

An incoming value differing from the one in force by more than `material_move_fraction` is
published, and recorded as a `MaterialMove`. Both parts matter: suppressing it would make the
tool quietly wrong, and accepting it silently would let a source's unit change or a schema drift
pass as a real epidemiological shift.

Material moves appear in `RefreshOutcome`, in the source status endpoint and in the interface's
data-health view. A scenario resolving a value that moved materially within the last refresh
carries `REFERENCE_MOVED` naming the previous and incoming figures.

### 5.5 Refresh runs on a schedule and on demand

```
POST /api/v1/reference/refresh          # all sources due under their cadence
POST /api/v1/reference/refresh/{source} # one source, now, regardless of cadence
```

A scheduled worker triggers each source at its `refresh_cadence_days`. Refreshes are serialised
per source — a second request for a source already running returns the running outcome rather
than starting a duplicate fetch. Credentials and proxy settings come from the environment
(non-negotiable 4); the proxy stays optional, as M0 established.

Being unable to reach a source is a normal condition, not an error state for the tool. The prior
published value stays in force, the attempt is recorded, and the status reports how old the
value being served is. **There is no hard-coded fallback number anywhere in the resolution
chain.** A wrong number that never expires is worse than a stale one that announces itself.

### 5.6 The market chooses the currency

Currency is a property of the market, not a field the user fills in. Selecting Germany sets EUR;
selecting India sets INR. The mapping is the `countries` table, and ARCHITECTURE.md §6.1 is its
seed.

```
calculation currency = the market's own currency, always
display currency     = the user's choice, defaulting to the market's own
```

Every calculation is performed in the market's own currency. Presentation converts, using the FX
set snapshotted into the run — never a rate looked up at render time, and never a rate fetched
during a calculation. A multi-market total shown in one currency is a presentation artefact and
is labelled with the FX set's fetch date, because the same run displayed a month later in USD
would otherwise appear to have changed.

Two rules that follow, and that the Streamlit prototype's free-text currency selector shows the
need for: a currency cannot be chosen independently of its market, and a mismatch is a type
error rather than a rendering quirk. `Money.__add__` already raises `CurrencyMismatchError`; the
market binding is what stops the mismatch being constructed in the first place.

### 5.7 Population and epidemiology fill themselves

No population input in the interface starts blank. Selecting a market resolves, through the
chain in ARCHITECTURE.md §7.3:

| Input | Source | Note |
|---|---|---|
| Total population | World Bank `SP.POP.TOTL` | Latest non-null year per country |
| Adult share | `1 − SP.POP.0014.TO.ZS/100` | Derived; the derivation is the provenance note |
| Under-18 population | Complement of the above | M18's paediatric denominator |
| Obesity prevalence | WHO `NCD_BMI_30A`, with 95% bounds | Bounds parameterise M9's PSA directly |
| Subgroup shares | `subgroup_prevalence` (M18) | Tier reflects how thin the evidence is |
| Diagnosis, treatment, access rates | `funnel_defaults` | Seeded, tier C, and visibly so |
| Health expenditure per capita | World Bank | M8's affordability denominator |

Each arrives as a `Valued` carrying source, vintage, tier and resolution level, and the
interface shows all four before the analyst touches anything (M21 §5.2). An override replaces
the value and keeps the original visible beside it.

A resolved value that does not exist is reported as absent, with the source that should have
supplied it named. It is not defaulted to zero, and it is not defaulted to another market's
value.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| Source unreachable | Prior value in force; `UNREACHABLE` status; `SOURCE_UNREACHABLE` warning with the age served |
| Source returns fewer rows than the last accepted run | Refresh rejected, `SUSPICIOUS_ROW_COUNT`, prior values held |
| Source returns a schema the transform does not recognise | Rejected at validate; nothing staged |
| Incoming value moves by more than the threshold | Published and flagged as a `MaterialMove` |
| Value past `max_age_days` | Served with `STALE_REFERENCE` naming the age |
| Value never fetched | `NEVER_FETCHED`; the parameter resolves to absent, not to zero |
| FX set older than 7 days at run creation | `STALE_FX`; the run proceeds and records the fetch date |
| FX rate missing for a required currency | Run creation is rejected — a run cannot snapshot an incomplete FX set |
| Refresh requested for a source already running | Returns the running outcome; no duplicate fetch |
| Prune would remove a staging row referenced by a run in retention | Row retained |
| Display currency set to a currency with no rate in the run's snapshot | Rejected, naming the snapshot date |

## 7. Data requirements

Creates `source_status` — one row per source with last attempt, last success, state, rows
published, message — and `refresh_runs`, one row per refresh with the `RefreshOutcome`.
`material_moves` records flagged changes with the previous and incoming values.

Every published reference table gains `fetched_at` where it lacks one, alongside the
`vintage_year` most already carry. `fx_rates` already carries `fetched_date` and needs nothing.

No table stores an API key, a proxy address or a connection string. Non-negotiable 4.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/reference/status` | Per-source freshness; no credentials in the payload |
| POST | `/api/v1/reference/refresh` | All sources due |
| POST | `/api/v1/reference/refresh/{source}` | One source, now |
| GET | `/api/v1/reference/status/moves` | Material moves, most recent first |
| GET | `/api/v1/reference/markets/{iso3}` | Resolved defaults for a market, with provenance |

`/reference/markets/{iso3}` is what makes §5.7 real for the frontend: one call returns every
pre-filled value for a market with its provenance, rather than the interface assembling it from
six endpoints and losing the labelling on the way.

## 9. Frontend

Shared, not a slice of its own — freshness belongs beside the value, not on a page of its own.

- `ProvenanceBadge` — source, vintage, tier and fetch age, on every resolved value
- `StalenessChip` — appears only when a value is past its policy, in words: "WHO diabetes
  prevalence, 2014 vintage, last checked 3 days ago"
- `DataHealthPanel` — one row per source with state and last success; a refresh action for a
  user with the right to trigger one
- Material moves surface here before they surface in a result

## 10. Test specification

| Class | Test |
|---|---|
| Unit | a value past `max_age_days` produces `STALE_REFERENCE` with the age |
| Unit | fetch age and vintage are reported separately; a fresh fetch of a 2014 vintage says both |
| Unit | a failed refresh leaves prior values in force and sets `UNREACHABLE` |
| Unit | a refresh returning fewer rows than the last accepted run is rejected |
| Unit | a move above the threshold publishes and records a `MaterialMove` |
| Unit | publish supersedes rather than updates — the prior row is still readable |
| Unit | selecting a market fixes its currency; an independent currency choice is rejected |
| Unit | a run with a missing FX rate for a required currency is rejected at creation |
| Unit | an absent reference value resolves to absent, never to zero or to another market |
| Unit | prune retains a staging row referenced by a run inside retention |
| Property | resolution is deterministic — the same market and vintage always resolve the same value |
| Integration | a run completed before a refresh still resolves to its snapshot afterwards |
| Integration | `/reference/markets/DEU` returns every funnel input with provenance in one call |
| CI | published reference row count for ten markets stays within the stated bound |

## 11. Acceptance criteria

- [ ] Every source has a stated cadence, max age and material-move threshold
- [ ] Fetch age and data vintage are reported as two different things
- [ ] A refresh publishes and supersedes; nothing is updated in place
- [ ] A failed or partial refresh leaves prior values in force and says so
- [ ] Large moves are published and flagged, never silently absorbed
- [ ] Staging is pruned on a retention policy, and runs in retention are protected
- [ ] Currency follows the market; display currency converts through the run's FX snapshot
- [ ] Every funnel input is pre-filled from published data with source, vintage, tier and level
- [ ] No hard-coded fallback value exists anywhere in the resolution chain
- [ ] No credential, proxy address or connection string is stored in the database or in source

## 12. Assumptions & open questions

**Assumptions.** Ten markets and one disease keep the published reference set small enough that
freshness can be managed per source rather than per row. The sources keep their current shapes
between refreshes; §6's schema check is what turns that assumption into a detected failure
rather than a silent one. A scheduled worker exists in the deployment — where it does not, the
on-demand endpoint plus the staleness warning still gives the analyst the truth.

**Open questions.**
1. Whether WHO's diabetes indicator should be replaced outright by the IDF Diabetes Atlas rather
   than projected forward from 2014. ARCHITECTURE.md §6.4 provides for a manual override;
   licensing is what has not been settled.
2. Whether material-move flagging should hold publication for review rather than publish and
   flag. Holding is safer and stops the tool self-updating, which is the point of the feature.
3. Whether display-currency conversion should be offered at all for multi-market totals, given
   that summing budget impact across health systems with different price bases is a figure with
   no payer behind it. The existing `MIXED_PRICE_BASIS` warning is the current mitigation.
