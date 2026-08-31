"""External evidence retrieval for EviTrack."""

from __future__ import annotations

import httpx

from ..schemas.evidence import EvidenceResult
from .sources.pubmed import PubMedSource
from .sources.registry import EvidenceSourceRegistry


PUBMED_EUTILS_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class EvidenceRepository:
    """Retrieve scientific evidence from public external sources."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=20.0,
            headers={
                "User-Agent": "BIET-EviTrack/0.1",
            },
        )

        self._source_registry = EvidenceSourceRegistry()
        self._source_registry.register(
            PubMedSource(self._client)
        )

    def close(self) -> None:
        """Close the HTTP client when this repository owns it."""
        if self._owns_client:
            self._client.close()

    def save(self, evidence: EvidenceResult) -> tuple[int, bool]:
        """Persist one evidence record without creating duplicates."""
        from sqlalchemy import select

        from ..dal.session import session_factory
        from ..models import EvidenceRecord

        with session_factory() as session:
            existing = None

            if evidence.source_id:
                existing = session.scalar(
                    select(EvidenceRecord).where(
                        EvidenceRecord.source == evidence.source,
                        EvidenceRecord.source_id == evidence.source_id,
                    )
                )

            if existing is not None:
                return int(existing.evidence_id), False

            record = EvidenceRecord(
                source=evidence.source,
                source_id=evidence.source_id,
                source_url=evidence.url,
                title=evidence.title,
                authors="; ".join(evidence.authors)
                if evidence.authors
                else None,
                publication_date=(
                    str(evidence.year)
                    if evidence.year is not None
                    else None
                ),
                doi=evidence.doi,
                evidence_type=evidence.evidence_type,
                abstract=evidence.abstract,
            )

            session.add(record)
            session.commit()
            session.refresh(record)

            return int(record.evidence_id), True

    def search(
        self,
        query: str,
        *,
        source: str = "pubmed",
        limit: int = 10,
    ) -> list[EvidenceResult]:
        """Search one registered external evidence source."""
        evidence_source = self._source_registry.get(source)
        return evidence_source.search(
            query,
            limit=limit,
        )

    def search_pubmed(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[EvidenceResult]:
        """Backward-compatible PubMed search wrapper."""
        return self.search(
            query,
            source="pubmed",
            limit=limit,
        )
