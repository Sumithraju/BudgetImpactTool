"""Guideline corpus retrieval — M10 section 5.3.

This module contains the one documented raw-SQL exception in the codebase
(biet-backend skill section 2). Everything else uses the ORM.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from biet_engine.models import RetrievedChunk


class GuidelineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, embedding: Sequence[float], *, k: int = 5) -> list[RetrievedChunk]:
        """The `k` nearest chunks to `embedding`, by cosine distance.

        Raw SQL, deliberately and exclusively: pgvector's `<=>` distance
        operator has no SQLAlchemy ORM expression, so there is nothing to
        compose a `select()` from. The embedding is passed as a bound
        parameter rather than interpolated — it is a 384-float vector, and
        building this string by concatenation is exactly the injection
        surface the ORM-only rule exists to close.

        Similarity is `1 - distance`, so it reads the way a reader expects:
        higher is closer.
        """
        vector = "[" + ",".join(str(float(x)) for x in embedding) + "]"

        rows = self._session.execute(
            text("""
                SELECT
                    c.chunk_id,
                    d.title           AS document_title,
                    d.issuing_body,
                    c.section,
                    c.page_number,
                    c.chunk_text,
                    1 - (c.embedding <=> CAST(:qemb AS vector)) AS similarity
                FROM guideline_chunks c
                JOIN guideline_documents d ON d.document_id = c.document_id
                ORDER BY c.embedding <=> CAST(:qemb AS vector)
                LIMIT :k
            """),
            {"qemb": vector, "k": k},
        ).all()

        return [
            RetrievedChunk(
                chunk_id=r.chunk_id,
                document_title=r.document_title,
                issuing_body=r.issuing_body,
                section=r.section,
                page_number=r.page_number,
                text=r.chunk_text,
                similarity=float(r.similarity),
            )
            for r in rows
        ]

    def count_chunks(self) -> int:
        """Zero means the corpus was never ingested — a `NO_GROUNDING`
        condition rather than a failure (M10 section 6)."""
        return int(
            self._session.execute(
                text("SELECT count(*) FROM guideline_chunks")
            ).scalar_one()
        )
