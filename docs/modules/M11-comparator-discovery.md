# M11 — Comparator Discovery

Module specification v1.0 · Owner area: Data + Backend · Depends on: M0, M4, M5

---

## 1. Purpose

Given a new asset's indication, molecular target and mechanism of action, retrieve the
therapies it would actually compete with — marketed and late-stage — from public
drug-discovery and regulatory sources, rank them by economic relevance, and hand the
selected basket to M4's market mix and M5's cost engine.

Today the comparator set is typed in by hand. That assumes the analyst already knows every
competitor, including the Phase III asset that will be on the market by the time this one
launches. For an early-stage asset that assumption is often wrong, and the cost of being
wrong is a budget impact computed against the wrong world-without.

## 2. Scope

**In scope.** Target resolution; candidate retrieval from Open Targets and ChEMBL;
classification into direct, therapeutic and pipeline competitors; relevance ranking;
selection into a scenario's comparator basket.

**Out of scope.** Deciding the basket — this module proposes, a human disposes (§5.6).
Pricing or regimen data for discovered drugs (§5.7 — they arrive without either).
Predicting clinical outcomes or market share. Adverse-event *probabilities*; M11 surfaces
which drugs exist, not how safe they are.

## 3. Dependencies

**Upstream.** Public APIs (§5.2), and M0's existing `drugs` table for matching a discovered
molecule to one already seeded.

**Downstream.** The selected basket becomes `CountryInput.therapies` via M1's resolution,
and therefore feeds M4's baseline shares and substitution vector and M5's cost computation.

## 4. Contracts

```python
class CompetitorClass(StrEnum):
    DIRECT = "direct"            # same indication + target + mechanism
    THERAPEUTIC = "therapeutic"  # same indication, different mechanism
    PIPELINE = "pipeline"        # not yet marketed; Phase II/III or under review
    EXCLUDED = "excluded"        # retrieved but not a plausible comparator


class ClinicalStage(StrEnum):
    APPROVAL = "APPROVAL"
    PHASE_3 = "PHASE_3"
    PHASE_2 = "PHASE_2"
    PHASE_1 = "PHASE_1"
    PRECLINICAL = "PRECLINICAL"


class DiscoveredDrug(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str                    # ChEMBL id, the stable cross-source key
    name: str
    drug_type: str | None             # "Small molecule", "Protein", ...
    max_clinical_stage: ClinicalStage
    mechanism_of_action: str | None
    action_type: str | None           # AGONIST, ANTAGONIST, INHIBITOR, ...
    target_symbol: str
    competitor_class: CompetitorClass
    relevance: float                  # 0-1, §5.5
    rationale: str                    # why it scored what it scored
    seeded_drug_id: int | None        # matched row in `drugs`, when one exists
    sources: tuple[str, ...]          # which APIs contributed


class ComparatorBasket(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_symbol: str
    target_id: str                    # Ensembl gene id
    indication_id: int
    direct: tuple[DiscoveredDrug, ...]
    therapeutic: tuple[DiscoveredDrug, ...]
    pipeline: tuple[DiscoveredDrug, ...]
    warnings: tuple[Warning_, ...]


# services/comparator_service.py
def discover(target: str, indication_id: int, *, mechanism: str | None) -> ComparatorBasket: ...
```

## 5. Logic specification

### 5.1 Target resolution

The user supplies a gene symbol (`GLP1R`) or an Ensembl id (`ENSG00000112164`). A symbol
resolves to an id through Open Targets' search; an id passes through unchanged. An
unresolvable symbol raises `UnknownTargetError` rather than returning an empty basket — an
empty result and a typo must not look the same.

### 5.2 Sources, and which is authoritative for what

| Source | Supplies | Verified |
|---|---|---|
| **Open Targets** (GraphQL) | `target.drugAndClinicalCandidates` — the candidate set, with clinical stage and drug type | 2026-08-24 |
| **ChEMBL** (REST) | `mechanism.json` — action type and mechanism text per molecule | 2026-08-24 |
| **Reactome** (REST) | `pathways/low/entity/{uniprot}` — signalling pathways containing the target (§5.9) | 2026-08-25 |
| ClinicalTrials.gov | Already ingested by M0; sponsor and trial status for pipeline entries (M14) | M0 |
| openFDA | Already ingested by M0; label metadata | M0 |

**Open Targets' schema has changed since this project began.** The field is
`drugAndClinicalCandidates`, not the `knownDrugs` that older documentation and most
training data describe, and `Drug.isApproved` / `maximumClinicalTrialPhase` no longer
exist — approval is read from `maxClinicalStage == APPROVAL`. The queries in
`comparator_repository.py` were verified against the live endpoint on the date above and
carry that date in a comment. **Re-verify before assuming a query still works**; a
GraphQL field rename fails loudly, which is the good case, but a silently renamed *enum
value* would not.

DrugCentral is deliberately not used: its offering is a bulk download rather than a
queryable API, and Open Targets plus ChEMBL already cover approval status and mechanism.

### 5.3 Classification

```
direct       same indication AND same target AND same action type
therapeutic  same indication, different target or action type
pipeline     max_clinical_stage is not APPROVAL
excluded     retrieved but the indication does not match
```

`pipeline` takes precedence over the other two: an unapproved drug cannot be part of the
world-without today, whatever its mechanism, but it is exactly what an asset launching in
four years will meet. Both facts matter and they are different facts, so they are
different buckets rather than one ranked list.

### 5.4 Same pathway is not the same as a comparator

The economically relevant question is *what would this patient receive if the new drug did
not exist*. That is not answered by pathway membership. Two drugs can share a signalling
pathway and never compete — different line of therapy, different severity, different
patient. So pathway proximity contributes to the score but never on its own promotes a
drug to `direct`.

### 5.5 Relevance score

A weighted mean over the factors that are actually known, rather than a fixed sum:

```
              Σ(k ∈ K) w_k · match_k
relevance =  ────────────────────────
                  Σ(k ∈ K) w_k
```

**Base factors**, always in play, and weighted to sum to 1.0 so that a discovery-only score is
unchanged by this formulation:

```
indication_match   0.40
target_match       0.25
mechanism_match    0.15
approval_match     0.15
seeded_match       0.05
```

**Optional factors**, in play only when the value exists — which means only for a candidate already
registered in M12 with curated commercial fields:

```
market_match           0.10    approved in at least one of the scenario's markets
line_of_therapy_match  0.10    same line as the modelled asset
```

Both are excluded from a bare discovery result rather than defaulted, because neither Open Targets
nor ChEMBL carries them and a default would be an invention. Scoring a candidate as line-matched
when nothing said so is worse than not scoring it at all: it produces a confident number from an
absence of evidence. Re-normalising over the factors in play means a registered candidate and an
unregistered one remain comparable, and the rationale states which factors participated.

`seeded_match` rewards a molecule already present in M0's `drugs` table — not because it
is more relevant clinically, but because it is the only kind that can enter a calculation
without further data entry (§5.7), and surfacing it first is honest about what the tool
can actually do next.

Weights are constants in `constants/comparator.py`, not literals.

### 5.6 The module proposes; a human disposes

Discovery returns candidates ranked. It does not write them into a scenario. Selection is
an explicit user action, because whether a drug is a real comparator depends on line of
therapy, local formulary position and clinical positioning — none of which any of these
databases knows.

The interface therefore presents the basket with checkboxes and a stated rationale per
row, never a pre-populated comparator set.

### 5.7 A discovered drug is not yet a usable comparator

Retrieval yields a molecule, a target and a stage. It does **not** yield a price, a
regimen, or a persistence figure — and M5 needs all three. A selected drug with no seeded
`drug_regimens` and `drug_prices` row cannot enter a calculation.

The basket states this per row. A discovered drug that matches a seeded one is
immediately usable; one that does not is flagged `needs_pricing`, and selecting it raises
`ComparatorNotPricedError` at scenario build rather than silently dropping it from the
market mix — a comparator that vanishes would understate the world-without and therefore
overstate budget impact.

### 5.8 Adverse-event costs are a separate, evidence-gated step

A better safety profile lowers adverse-event management cost, and M5 already accepts
`ae_cost` and `offset` per therapy. M11 does **not** populate them, and must not: doing so
would mean this tool asserting a clinical claim it has not established.

The supported flow is that a user enters an AE cost differential *supported by trial or
label evidence*, and the seeded value carries that citation and its confidence tier like
every other input. What the tool says is "when evidence indicates a different AE profile,
its cost consequences are modelled" — never "this drug will have fewer side effects".

### 5.9 Pathway membership

Reactome maps a target's UniProt accession to the signalling pathways containing it. A candidate
acting on a *different* target in a *shared* pathway is retrieved and scored, and this is the only
mechanism by which such a candidate is found at all — target-based retrieval alone would miss it.

Pathway membership contributes to relevance and never promotes a candidate to `direct`, for the
reason given in §5.4. It is also the most expensive part of discovery: it requires a second
resolution step (symbol → UniProt) and a pathway query per target, so it is opt-in via
`include_pathway`, and its failure degrades to a pathway-free basket with `PARTIAL_DISCOVERY`
rather than failing the request.

Pathway ids travel with the candidate so that M12 can persist them, and so a reader can check the
claim: a rationale that says "shares Reactome R-HSA-420092" is verifiable, and one that says
"related pathway" is not.


## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| Unresolvable target symbol | Raise `UnknownTargetError` naming the symbol |
| Target resolves, zero candidates | Empty basket + `NO_COMPARATORS_FOUND` warning — not an error |
| An upstream API is unreachable | Return what the other sources gave, with `PARTIAL_DISCOVERY` naming the failed source |
| Both APIs unreachable | Raise `UpstreamUnavailableError` (503) — an empty basket would read as "no competitors" |
| Discovered drug matches a seeded row | Link `seeded_drug_id`; usable immediately |
| Discovered drug has no seeded row | `needs_pricing`; selecting it raises at scenario build |
| Same molecule from both sources | Deduplicate on ChEMBL id, union the `sources` tuple |
| Pipeline drug selected as a comparator | Permitted — but it is not part of the world-without today, and the basket says so |

## 7. Data requirements

Reads M0's `drugs` for seeded matching. Writes nothing: discovery is a read-through to
public APIs and is not persisted as reference data, because the answer changes as trials
progress and a cached basket would quietly go stale.

Responses are cached in-process for the duration of a request only.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/comparators/discover` | `?target=GLP1R&indication_id=1&mechanism=agonist` |
| GET | `/api/v1/comparators/targets/{symbol}` | Resolve a symbol to an Ensembl id |

## 9. Frontend

Slice `features/comparator-discovery/`.

- `TargetInput` — symbol or Ensembl id, with resolution feedback
- `ComparatorBasket` — three grouped lists (direct, therapeutic, pipeline), each row
  showing stage, mechanism, relevance, rationale, and whether it is priced
- Unpriced rows are visibly distinct and carry a "needs pricing" marker; selecting one
  explains what is missing rather than failing later

## 10. Test specification

| Class | Test |
|---|---|
| Unit | classification: same target + action + indication → `direct` |
| Unit | same indication, different action type → `therapeutic` |
| Unit | `maxClinicalStage != APPROVAL` → `pipeline`, whatever the mechanism |
| Unit | different indication → `excluded` |
| Unit | relevance weights sum to 1.0 |
| Unit | a seeded match scores above an identical unseeded one |
| Unit | deduplication unions `sources` rather than keeping two rows |
| Unit | unresolvable symbol raises `UnknownTargetError` |
| Unit | zero candidates → empty basket + `NO_COMPARATORS_FOUND`, not an exception |
| Unit | one source failing → `PARTIAL_DISCOVERY` naming it |
| Unit | both sources failing → `UpstreamUnavailableError` |
| Contract | every returned drug carries a non-empty `rationale` |
| Integration | GLP1R returns semaglutide and tirzepatide as approved, retatrutide as pipeline |

Live-API tests are marked `network` and skipped by default, exactly like M0's ingestion
tests: the offline suite must stay offline. Classification and ranking are pure and are
tested against recorded fixtures.

## 11. Acceptance criteria

- [x] A gene symbol yields a ranked, classified basket
- [x] Direct, therapeutic and pipeline are separated, not merged into one list
- [x] Every row carries a rationale a reader can check
- [x] Unpriced drugs are flagged, and selecting one fails loudly at build rather than silently
- [x] Discovery never writes a comparator into a scenario by itself
- [x] An upstream outage degrades to a partial basket, never to a silent empty one
- [x] Offline test suite stays offline

## 12. Assumptions & open questions

**Assumptions.** Open Targets and ChEMBL remain freely queryable without authentication.
Target-based discovery is a reasonable proxy for competitive overlap in this therapy area;
it is weaker where competition is driven by route or setting rather than mechanism.

**Open questions.**
1. Whether pipeline competitors should influence the *baseline* mix in later years — a
   Phase III asset launching before this one arguably belongs in the world-without by
   year 3. Currently they are discoverable but not automatically modelled, which is the
   conservative reading.
2. Whether to cache baskets with a short TTL. Not persisted today (§7) on the grounds
   that trial status changes; if discovery latency becomes a problem, a TTL is the
   answer rather than a permanent table.
