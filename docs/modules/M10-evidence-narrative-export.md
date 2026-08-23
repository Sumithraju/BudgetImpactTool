# M10 — Evidence, Narrative & Export

Module specification v1.0 · Owner area: Backend + AI · Depends on: M7, M8, M9

---

## 1. Purpose

Ground outputs in published methodological guidance, compose an executive narrative constrained to
the computed results, and produce distributable deliverables carrying the full assumption register.

## 2. Scope

**In scope.** Guideline corpus ingestion and chunking; vector retrieval; cited narrative
generation; a scoped conversational copilot; PDF and PowerPoint export including the assumption
register and citation list.

**Out of scope.** Any calculation. Any number generation by a language model — see §5.1.

## 3. Dependencies

Consumes `EngineResult` (M7), `AffordabilityResult` and `PriceCorridor` (M8), `OwsaResult` and
`PsaResult` (M9). Consumes the corpus indexed by M0.

## 4. Contracts

```python
class RetrievedChunk(BaseModel):
    model_config = ConfigDict(frozen=True)
    chunk_id: int
    document_title: str
    issuing_body: str               # ISPOR | NICE | WHO | CDA-AMC
    section: str | None
    page_number: int | None
    text: str
    similarity: float


class Narrative(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: UUID
    sections: Mapping[str, str]     # population | impact | affordability | uncertainty | limitations
    citations: tuple[RetrievedChunk, ...]
    model_id: str
    generated_at: datetime
```

## 5. Logic specification

### 5.1 The model does not produce numbers

**Every quantitative value in generated text originates from the deterministic engine** and is
injected into the prompt as structured context. The model is instructed to reproduce supplied
figures verbatim and is prohibited from computing, inferring, estimating or rounding any value.

This boundary is absolute. The credibility of a budget impact estimate rests entirely on its
arithmetic being traceable; a generated number is by definition untraceable. Enforcement is
two-layer:

1. **Prompt constraint** — explicit instruction, with the structured results supplied as JSON.
2. **Post-generation validation** — extract every numeric token from the generated text and assert
   each appears in the supplied context. An unmatched number fails generation and returns an error
   rather than the text. Log the failure with the offending token.

### 5.2 Corpus and chunking

| Document | Body |
|---|---|
| Principles of Good Practice for Budget Impact Analysis | ISPOR |
| Budget Impact Analysis — Principles of Good Practice II (2012 Task Force) | ISPOR |
| Budget impact analysis editorial (2014) | ISPOR |
| Company budget impact analysis submission template | NICE |
| Budget impact test procedure | NICE |
| Budget impact analysis teaching materials | WHO |

```
PDF/DOCX → text extraction → section-aware chunking (800 tokens, 100 overlap)
         → embedding (BAAI/bge-small-en-v1.5, 384-dim)
         → pgvector with document, section and page metadata
```

Chunks preserve section headings so citations can name a section, not just a page. Chunking that
splits mid-sentence at the token boundary is acceptable; chunking that loses the page number is not.

### 5.3 Retrieval

Embed the query, retrieve top `k` by cosine similarity (default 5), filter below a similarity floor
of 0.35, return with document title, issuing body, section and page.

Retrieval is the one place raw SQL is permitted outside migrations, because pgvector's `<=>`
operator has no SQLAlchemy ORM expression. It lives in a single repository method, fully
parameterised, with a comment stating why (see the `biet-backend` skill, §2).

### 5.4 Narrative structure

Five sections, generated in one call:

| Section | Content |
|---|---|
| `population` | The funnel: how the addressable population was derived, with the stages and their sources |
| `impact` | Incremental budget impact by market and year; the net cost per patient switched |
| `affordability` | Position against national health expenditure; band; binding market if a corridor was run |
| `uncertainty` | The top three tornado drivers and the PSA credible interval |
| `limitations` | Stated model limitations — see §5.5 |

### 5.5 Mandatory limitations

Every narrative and every export includes these, drawn from the modules that own them. They are not
optional and are not subject to the model's discretion:

- Persistence is applied at the first-year fraction uniformly across the horizon, which understates
  later-year consumption and is therefore conservative (M6 §5.3).
- Costs are constant across the horizon; no price erosion or loss of exclusivity (M5 §12).
- Eligibility criteria are combined assuming conditional independence (M3 §12).
- PSA samples parameters independently; no correlation structure (M9 §12).
- Affordability is assessed against **total** health expenditure, not a pharmaceutical budget
  subset (M8 §12).
- Any market whose price is PPP-derived rather than observed is flagged individually (M5 §5.3).
- Any input with a stale vintage, a projected value, or tier-D confidence is named explicitly
  (M1 §5.3).

### 5.6 Copilot

Conversational surface over the same retrieval index, scoped to two things: methodological
questions ("how should source of business be handled under ISPOR guidance?") and interpretation of
the current run's results.

- Read access to the active run's structured results and the guideline index.
- **No** ability to modify a scenario, trigger a calculation, or write anything.
- Same numeric constraint and post-generation validation as §5.1.
- Out-of-scope questions are declined with a short statement, not answered from general knowledge.

### 5.7 Export

| Format | Contents |
|---|---|
| PDF (ReportLab) | Title, scenario definition, funnel per market, impact tables and charts, affordability, corridor, tornado, PSA, **complete assumption register**, citation list, limitations |
| PPTX (python-pptx) | Executive subset: headline impact, affordability position, corridor, top three drivers, limitations |

The **assumption register** is a table of every resolved input: parameter path, market, value,
source, vintage, confidence tier and resolution level. It is generated from the run snapshot, not
from the live database, so an export of an old run reflects what that run actually used.

Exports are generated from a stored `run_id`, never from a live recalculation, so the document and
the numbers it cites can never drift apart.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| Generated text contains a number absent from context | Fail generation, return error, log the token |
| Retrieval returns nothing above the similarity floor | Generate without citations, warn `NO_GROUNDING` |
| LLM API unavailable | Return 503 with a clear message; results and exports remain available without narrative |
| Export requested for a `run_id` that does not exist | 404 |
| Narrative requested before any run exists | 409 with guidance to calculate first |
| Copilot asked to change a scenario | Decline; state it is read-only |
| Corpus not yet indexed | 503 with a clear operational message |

## 7. Data requirements

`guideline_documents`, `guideline_chunks` with the ivfflat index (ARCHITECTURE.md §8.3), and
`model_runs` for the snapshot an export is built from. Generated narratives are stored against
their `run_id` so text and numbers stay bound together.

## 8. API surface

| Method | Path |
|---|---|
| POST | `/api/v1/evidence/search` |
| POST | `/api/v1/scenarios/{id}/narrative` |
| POST | `/api/v1/evidence/copilot` |
| POST | `/api/v1/scenarios/{id}/export/pdf` |
| POST | `/api/v1/scenarios/{id}/export/pptx` |

Narrative and export take a `run_id`; absent one, they use the latest forward run.

## 9. Frontend

Slice `features/evidence-copilot/`.

- `NarrativePanel` — the five sections, with inline citation chips that expand to the source
  passage, document, section and page
- `CopilotChat` — scoped conversation; a visible note that it is read-only
- `ExportButton` — format selection and progress; downloads are served from the API, not
  constructed client-side
- Citations always show issuing body and page. A citation the reader cannot verify is not a citation.

## 10. Test specification

| Class | Test |
|---|---|
| Unit | chunking preserves page number and section heading |
| Unit | similarity floor excludes a chunk at 0.30, includes one at 0.40 |
| Unit | numeric validator rejects text containing an unsupplied number |
| Unit | numeric validator accepts text reproducing supplied numbers exactly |
| Unit | numeric validator tolerates formatting variants of a supplied number (1234567 / 1,234,567) |
| Unit | all seven mandatory limitations appear in every narrative |
| Unit | assumption register is built from the run snapshot, not the live database |
| Integration | export for a stored run reproduces that run's numbers, not current reference data |
| Integration | LLM unavailable → 503; calculation endpoints unaffected |
| Integration | retrieval with no results above floor → narrative generated with `NO_GROUNDING` |
| Contract | copilot declines a scenario-modification request |

The numeric validator tests are the most important in this module. They are what enforce §5.1.

## 11. Acceptance criteria

- [ ] Corpus indexed; retrieval returns cited passages with body, section and page
- [ ] Narrative generated with all five sections
- [ ] Post-generation numeric validation implemented and passing its tests
- [ ] All seven mandatory limitations present in every narrative and export
- [ ] Copilot is read-only and declines out-of-scope requests
- [ ] PDF and PPTX generated from a stored run snapshot
- [ ] Assumption register complete: path, market, value, source, vintage, tier, resolution level
- [ ] LLM outage degrades gracefully — results and exports still work
- [ ] Raw SQL confined to the single documented pgvector method

## 12. Assumptions & open questions

**Assumptions.** The guideline corpus is static and publicly distributable. Narrative is generated
in English only. Retrieval quality is adequate at `k = 5`; no reranker.

**Open questions.**
1. Whether narratives should be regenerable on demand or frozen once generated. Currently stored
   per run; a regenerate action would create a second narrative against the same run, which is
   acceptable provided both are retained.
2. Whether the copilot needs access to prior runs for comparison, or only the active one. Active
   only for launch.
