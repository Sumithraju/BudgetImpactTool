"""EviTrack external evidence discovery endpoints.

EviTrack is intentionally isolated from the deterministic BIA calculation
workflow.

Current MVP:
    User query
        -> PubMed
        -> normalized EvidenceResult records
        -> frontend for review

External evidence is discovery/supporting evidence only. It does not
automatically become a BIA input.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..repositories.evidence import EvidenceRepository

router = APIRouter(
    prefix="/api/v1/evitrack",
    tags=["evitrack"],
)


@router.get("/evidence")
def list_evidence(
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Return previously saved EviTrack evidence records."""
    from sqlalchemy import select

    from ..dal.session import session_factory
    from ..models import EvidenceRecord

    with session_factory() as session:
        records = session.scalars(
            select(EvidenceRecord)
            .order_by(EvidenceRecord.evidence_id.desc())
            .limit(limit)
        ).all()

    return {
        "count": len(records),
        "results": [
            {
                "evidence_id": record.evidence_id,
                "title": record.title,
                "source": record.source,
                "source_id": record.source_id,
                "source_url": record.source_url,
                "authors": (
                    record.authors.split("; ")
                    if record.authors
                    else []
                ),
                "publication_date": record.publication_date,
                "doi": record.doi,
                "evidence_type": record.evidence_type,
                "abstract": record.abstract,
            }
            for record in records
        ],
    }


@router.post("/evidence")
def add_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Save one externally discovered evidence record."""
    from ..schemas.evidence import EvidenceResult

    item = EvidenceResult.model_validate(evidence)
    repository = EvidenceRepository()

    try:
        evidence_id, _created = repository.save(item)
    finally:
        repository.close()

    return {
        "status": "saved",
        "evidence_id": evidence_id,
        "evidence": item.model_dump(),
    }


@router.get("/health")
def health() -> dict[str, Any]:
    """Confirm that EviTrack is registered and available."""
    return {
        "module": "evitrack",
        "status": "ok",
    }


@router.get("/sources")
def list_sources() -> dict[str, Any]:
    """Return the external evidence sources registered with EviTrack."""
    repository = EvidenceRepository()

    try:
        names = repository._source_registry.names()
    finally:
        repository.close()

    return {
        "sources": [
            {"name": name}
            for name in names
        ]
    }


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=500),
    source: str = Query(default="pubmed", min_length=1),
    limit: int = Query(default=10, ge=1, le=25),
) -> dict[str, Any]:
    """Search external scientific evidence.

    PubMed is the first external source in the EviTrack MVP.

    This endpoint deliberately does not touch:
    - BIA calculations
    - scenarios
    - engine inputs
    - evidence-gap ranking
    - narrative generation
    - BIA persistence

    It discovers external evidence and persists the discovered
    records for later review.
    """
    query = q.strip()

    if not query:
        return {
            "query": q,
            "results": [],
        }

    repository = EvidenceRepository()

    try:
        results = repository.search(
            query,
            source=source,
            limit=limit,
        )

        saved_ids: list[int] = []
        new_count = 0
        existing_count = 0

        for result in results:
            evidence_id, created = repository.save(result)
            saved_ids.append(evidence_id)

            if created:
                new_count += 1
            else:
                existing_count += 1
    finally:
        repository.close()

    return {
        "query": query,
        "source": results[0].source if results else source,
        "saved_count": len(saved_ids),
        "new_count": new_count,
        "existing_count": existing_count,
        "results": [
            result.model_dump()
            for result in results
        ],
    }
