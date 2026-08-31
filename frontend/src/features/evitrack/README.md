# EviTrack

EviTrack is BIET's external scientific evidence discovery and curation
workspace.

It is intentionally separated from the deterministic Budget Impact Analysis
(BIA) calculation workflow.

## Purpose

EviTrack helps an analyst:

    Search
      ->
    Review
      ->
    Select
      ->
    Curate
      ->
    Potential future BIA input

Evidence discovered through EviTrack does **not** automatically modify BIA
inputs, scenarios, assumptions, or calculation results.

Human review remains required before evidence can be considered for use in a
BIA parameter.

## Current MVP

The current implementation provides:

- External scientific evidence search.
- PubMed / NCBI as the current evidence provider.
- Normalized evidence records.
- Evidence persistence in PostgreSQL.
- Duplicate prevention using source + source ID.
- Evidence listing.
- Individual evidence saving.
- Registered evidence-source discovery.
- EviTrack health endpoint.
- Frontend evidence search and curation workspace.
- Direct links to the original public evidence source.

The current implementation does not require an LLM or a separate vector
database.

## Backend API

Base path:

    /api/v1/evitrack

### Health

    GET /api/v1/evitrack/health

### Search

    GET /api/v1/evitrack/search

Example:

    curl -sS -G \
      "http://localhost:8077/api/v1/evitrack/search" \
      --data-urlencode "q=obesity semaglutide budget impact" \
      --data-urlencode "limit=5"

Supported query parameters:

- `q` — evidence search query.
- `source` — registered evidence source; currently `pubmed`.
- `limit` — number of results, maximum 25.

The search operation retrieves normalized evidence and persists the discovered
records without creating duplicates.

### Saved evidence

    GET /api/v1/evitrack/evidence

Returns previously saved EviTrack evidence records.

### Save evidence

    POST /api/v1/evitrack/evidence

Persists a normalized evidence record. Existing records are not duplicated.

### Evidence sources

    GET /api/v1/evitrack/sources

Returns the evidence sources registered with EviTrack.

## Evidence record

The persisted `EvidenceRecord` contains:

- `evidence_id`
- `source`
- `source_id`
- `source_url`
- `title`
- `authors`
- `publication_date`
- `doi`
- `evidence_type`
- `abstract`

The database enforces uniqueness for records that have a source identifier,
using:

    source + source_id

## Backend structure

Relevant implementation files:

    backend/src/biet_api/routes/evitrack.py
    backend/src/biet_api/repositories/evidence.py
    backend/src/biet_api/repositories/sources/pubmed.py
    backend/src/biet_api/repositories/sources/registry.py
    backend/src/biet_api/models/evidence.py
    backend/src/biet_api/schemas/evidence.py

Database migration:

    backend/alembic/versions/f3593de96a10_add_evitrack_evidence_records.py

Tests:

    backend/tests/api/test_evitrack_evidence.py

## Frontend structure

EviTrack frontend code is isolated under:

    frontend/src/features/evitrack/

The feature contains the evidence-search interface and evidence workspace.

## Architecture principle

EviTrack is an evidence-support layer, not an automatic evidence-to-model
pipeline.

The intended future workflow is:

    External evidence
          |
          v
    Evidence record
          |
          v
    Analyst review
          |
          v
    Applicability assessment
          |
          v
    BIA parameter mapping
          |
          v
    Provenance recorded
          |
          v
    Deterministic BIA engine

This separation prevents an external publication from silently changing a
model assumption.

## Extensibility

The evidence repository uses a source registry.

The current registered source is:

    pubmed

Additional public evidence sources can be added through the source registry
without coupling the external provider directly to the EviTrack API route.

The architecture is therefore intended to support additional countries,
markets, and public evidence sources as BIET expands beyond its current market
set.

## Verification

The complete backend test suite currently passes:

    550 passed, 4 warnings

The warnings are existing pytest/dependency warnings and do not represent test
failures.
