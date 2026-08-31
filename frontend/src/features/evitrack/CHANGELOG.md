# EviTrack CHANGELOG

2026-08-31

Verification
------------

- Re-verified the EviTrack frontend and backend documentation against the
  current implementation.
- Confirmed that EviTrack remains isolated from the deterministic BIET BIA
  calculation workflow.
- Confirmed that external evidence does not automatically modify BIA inputs.
- Confirmed the current evidence workflow:
  search -> review -> select -> curate -> potential future BIA input.
- Confirmed PubMed / NCBI is the current registered external evidence source.
- Confirmed evidence records are persisted in PostgreSQL.
- Confirmed duplicate prevention using source + source ID.
- Confirmed the following EviTrack endpoints:
    GET  /api/v1/evitrack/health
    GET  /api/v1/evitrack/search
    GET  /api/v1/evitrack/evidence
    POST /api/v1/evitrack/evidence
    GET  /api/v1/evitrack/sources
- Confirmed the full backend test suite:
    550 passed, 4 warnings.

Implementation
--------------

- Added the `EvidenceRecord` database model.
- Added the EviTrack evidence repository.
- Added the registered evidence-source architecture.
- Added the PubMed source implementation.
- Added EviTrack API routes for discovery and persistence.
- Added the EviTrack evidence schema.
- Added the database migration for `evidence_records`.
- Added frontend EviTrack evidence-search and curation functionality.
- Added backend API tests for EviTrack evidence functionality.

Design
------

EviTrack remains a curation layer rather than an automatic evidence-to-input
pipeline.

External evidence must be reviewed for:

- population
- geography
- indication
- treatment setting
- comparator
- outcome definition
- time horizon
- source vintage
- applicability to the intended BIA parameter

Evidence discovered by EviTrack therefore remains separate from deterministic
BIA calculations until an analyst explicitly decides to use it.

Future expansion
----------------

The source-registry architecture is intentionally extensible.

Additional public evidence providers and additional countries/markets can be
introduced without changing the fundamental EviTrack governance principle:

    Discover
      ->
    Review
      ->
    Curate
      ->
    Potential BIA input

2026-08-30

Overview
--------

EviTrack progressed from an internal guideline-search scaffold into a working
external scientific evidence discovery and curation MVP.

The implementation remains isolated from the deterministic BIET BIA
calculation workflow.

The central design rule remains:

    Evidence discovery
        ->
    Human review
        ->
    Evidence curation
        ->
    Potential future BIA input

Retrieved evidence does not automatically modify BIA assumptions.
