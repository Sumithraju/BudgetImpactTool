# M12 — Comparator Registry and Asset Intake

Module specification v1.0 · Owner area: Backend + Data · Depends on: M0, M5, M11

---

## 1. Purpose

Capture the new asset once, hold the single drug–target–market record for every comparator the
system knows about, and promote a discovered molecule into one that can enter a calculation.

M11 returns molecules. M5 needs prices, regimens and persistence. Nothing in Open Targets, ChEMBL
or Reactome carries any of the three, and no amount of further retrieval will produce them — a US
net price is not a public fact. The registry is where a retrieved molecule and a curated commercial
record become one row, and promotion is the explicit act that makes that row usable.

## 2. Scope

**In scope.** New-asset intake with public-source pre-fill; the `comparator_assets` record and its
per-market approvals; promotion into `drugs`, `drug_regimens` and `drug_prices`; the guard that
rejects an unpromoted comparator at scenario build.

**Out of scope.** Discovery itself (M11). Adverse-event data (M13). Deciding a price — the module
records what a user supplies with its stated basis and tier; it does not estimate one. M5's
purchasing-power derivation remains the only mechanism that produces an unobserved price, and it
labels its output as derived.

## 3. Dependencies

**Upstream.** M11 for discovered candidates; M0's `drugs`, `drug_regimens`, `drug_prices`,
`countries`, `indications`.

**Downstream.** M1's resolution reads promoted comparators into `CountryInput.therapies`; M4's
baseline mix and substitution vector are defined over their `drug_id`s; M13 attaches adverse-event
profiles to the same `drug_id`; M14 reads `expected_entry_year` and `assumed_terminal_pct`.

## 4. Contracts

```python
class LineOfTherapy(StrEnum):
    FIRST = "first"
    SECOND = "second"
    THIRD_PLUS = "third_plus"
    ANY = "any"


class AssetIntake(BaseModel):
    """The new asset. Everything the public sources can supply is pre-filled
    from M11; the user confirms rather than types."""

    asset_name: str
    indication_id: int
    target_symbol: str
    mechanism_of_action: str | None
    action_type: str | None
    route: str | None
    dose_amount: float | None
    dose_unit: str | None
    admins_per_year: float | None
    expected_launch_year: int
    country_codes: tuple[str, ...]


class PromotionRequest(BaseModel):
    """What a discovered molecule needs before it can be a comparator."""

    regimen: RegimenInput                   # units_per_admin, admins_per_year, wastage, persistence
    prices: tuple[PriceInput, ...]          # one per market, each with basis, source, tier


class RegisteredAsset(BaseModel):
    asset_id: int
    source_id: str
    asset_name: str
    competitor_class: CompetitorClass
    drug_id: int | None                     # null until promoted
    is_promoted: bool
    missing_for_promotion: tuple[str, ...]  # "regimen", "price:USA", ...
    approvals: tuple[MarketApproval, ...]
    provenance: Provenance
```

```python
# services/comparator_registry_service.py
def register(candidate: DiscoveredDrug | AssetIntake) -> RegisteredAsset: ...
def promote(asset_id: int, request: PromotionRequest) -> RegisteredAsset: ...
def list_assets(indication_id: int, *, klass: CompetitorClass | None) -> list[RegisteredAsset]: ...
def require_promoted(drug_ids: Sequence[int]) -> None: ...   # raises ComparatorNotPricedError
```

## 5. Logic specification

### 5.1 Asset intake

The user supplies, at minimum, **indication and target or molecule**. Everything else that a public
source can answer is retrieved through M11 and presented pre-filled: mechanism, action type, drug
type, clinical stage, pathway membership. The user confirms or corrects each field, and a corrected
field's provenance changes from the retrieval source to `user` with the tier the user states.

Fields no public source can supply — expected launch year, target markets, line of therapy,
intended dose where the asset is pre-registrational — are entered directly and are tier C or D by
construction. The interface does not pretend otherwise.

The new asset is stored as a `comparator_assets` row with `is_new_asset = true`. It is the same
shape as a comparator because it is the same kind of thing; what differs is which side of the
world-with/world-without boundary it sits on, and that is M1's business, not the registry's.

### 5.2 The registry record

One row per `(source_id, indication_id)`. The same molecule in two indications is two records,
because its line of therapy, comparator set and relevance differ between them.

Columns divide into three groups by who writes them:

| Group | Written by | Tier |
|---|---|---|
| Mechanistic — target, action type, mechanism, pathway, stage, drug type | M11 retrieval | B, source-stamped and dated |
| Commercial — brand, manufacturer, line of therapy, market approvals | Curator | As stated, usually B or C |
| Economic — regimen, prices | Promotion (§5.3) | As stated per value |

A curator-written value never silently overwrites a retrieved one: the retrieved value and its
retrieval date stay in the row, and the override is recorded with its own source. This is the same
rule as M1's scenario overrides, applied to reference data.

### 5.3 Promotion

Promotion is a single transaction that writes:

1. A `drugs` row — name, generic name, company, class, route, indication, `is_comparator`.
2. Exactly one `drug_regimens` row — units per administration, administrations per year, wastage,
   twelve-month persistence, source, tier.
3. One `drug_prices` row per market — local price, currency, basis, gross-to-net where the basis is
   an estimated net, source, URL, tier.

and sets `comparator_assets.drug_id`. All of it or none of it: a comparator with a regimen and no
price is not usable, and a half-promoted asset that looks promoted is worse than one that plainly is
not.

Re-promoting an already-promoted asset updates the regimen and prices in place rather than creating
a second `drugs` row. `uq_drugs_name` would reject the duplicate anyway; failing on a unique
constraint is not an acceptable way to express a business rule.

### 5.4 What "usable" means, precisely

An asset is usable in market `c` when it has a `drug_id`, a regimen, and a price row for `c` — or a
price in the reference market from which M5 can derive one. The three are checked separately and
`missing_for_promotion` names each gap by market, so the interface can say "needs a German price"
rather than "not ready".

### 5.5 Feeding the engine

Nothing in this module calls the engine. It makes rows that M1's resolution already knows how to
read: once an asset is promoted, its `drug_id` appears in `/reference/drugs`, can be named in a
scenario's comparator set, receives a baseline share in M4, a substitution weight in the source-of-
business vector, a cost in M5, a persistence fraction in M6, and therefore a place in M7's
world-without. No new engine contract is required, which is the point — the registry exists so that
discovery lands in the shape the engine already accepts.

### 5.6 The guard

`require_promoted` is called at scenario build with every comparator `drug_id` the scenario names.
An unpromoted one raises `ComparatorNotPricedError` naming the asset and what it is missing.

Dropping it instead would be the silent failure this system exists to avoid: a comparator absent
from the world-without means its cost is never subtracted, and budget impact is overstated by
exactly the cost of the care the new therapy displaces.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| Register a molecule already registered for this indication | Return the existing record; do not duplicate |
| Same molecule, different indication | A second record — different comparator set, different relevance |
| Promote with no price for a named market | `ValidationError` naming the market |
| Promote with a persistence outside (0, 1] | Rejected by the `drug_regimens` check constraint and by the schema |
| Promote an asset whose name collides with an existing `drugs` row | Link to the existing row rather than creating a second |
| Price basis `estimated_net` without a gross-to-net ratio | Rejected — a stated net price must say what assumption produced it |
| Unpromoted comparator named in a scenario | `ComparatorNotPricedError` at build, naming the gap |
| Delete an asset that has been promoted and used in a run | Refused — runs are immutable and must stay reproducible |

## 7. Data requirements

Creates `comparator_assets` and `comparator_approvals` (ARCHITECTURE.md §8.4). Writes `drugs`,
`drug_regimens` and `drug_prices` on promotion. Alembic migration required and reversible.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/comparators/assets` | `?indication_id=1&competitor_class=direct` |
| POST | `/api/v1/comparators/assets` | Register an asset or a discovered comparator, 201 |
| GET | `/api/v1/comparators/assets/{id}` | One record with its promotion gaps |
| POST | `/api/v1/comparators/assets/{id}/promote` | Regimen + prices, atomic |

## 9. Frontend

Slice `features/comparator-discovery/` (shared with M11).

- `AssetIntakeForm` — indication and target first; the rest pre-filled from discovery and confirmable
- `RegistryTable` — assets with class, stage, promotion state and what is missing
- `PromotionDrawer` — regimen and per-market price entry, each field demanding a source and tier
- Unpromoted rows are visibly distinct everywhere they appear, including in the scenario builder

## 10. Test specification

| Class | Test |
|---|---|
| Unit | registering the same `(source_id, indication_id)` twice returns one record |
| Unit | the same molecule under two indications yields two records |
| Unit | `missing_for_promotion` names each market lacking a price |
| Unit | promotion is atomic — a failing price write leaves no `drugs` row |
| Unit | re-promotion updates in place rather than duplicating |
| Unit | promotion links to an existing `drugs` row on a name collision |
| Unit | `require_promoted` raises `ComparatorNotPricedError` naming the asset |
| Integration | register → promote → the asset appears in `/reference/drugs` |
| Integration | a promoted comparator receives a baseline share and a cost in a calculation |
| Contract | curator override does not erase the retrieved value or its retrieval date |

## 11. Acceptance criteria

- [x] A user enters indication and target, and the rest of the asset arrives pre-filled
- [x] One record per molecule per indication, with retrieved and curated values distinguishable
- [x] Promotion is atomic and writes regimen and prices with source and tier on every value
- [x] Promotion gaps are named per market, not reported as a single boolean
- [x] An unpromoted comparator fails scenario build loudly and by name
- [x] A promoted comparator flows into M4, M5 and M7 with no new engine contract

## 12. Assumptions & open questions

**Assumptions.** Generic name is a sufficient key between a discovered molecule and a seeded drug
row; it holds for small molecules and peptides and is weaker for biologics with divergent
international non-proprietary naming.

**Open questions.**
1. Whether market approval should gate comparator selection automatically — a drug not approved in
   Germany cannot be in the German world-without, and today that is the curator's judgement rather
   than an enforced rule. Enforcing it needs approval data with better coverage than is currently
   seeded.
2. Whether a promoted asset should be versioned when its price changes, or simply updated. Runs
   snapshot their resolved inputs, so reproducibility does not require it; auditability might.
