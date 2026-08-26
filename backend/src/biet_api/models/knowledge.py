"""Guideline corpus — ARCHITECTURE.md section 8.3.

Schema is created in Phase 1; the corpus itself is ingested and embedded in
Phase 5 (ARCHITECTURE.md section 15). Retrieval is the only place in the system
where raw SQL is permitted outside a migration, because pgvector's `<=>` distance
operator has no ORM expression.
"""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, SmallInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

#: Dimensionality of the sentence-transformer embedding. Fixed by the model
#: choice (BAAI/bge-small-en-v1.5 via fastembed, 384 dimensions); changing it
#: requires a migration and a full re-embed.
EMBEDDING_DIMENSIONS = 384

#: ivfflat list count. Rule of thumb is rows/1000 for under a million rows; the
#: corpus is small enough that 100 is comfortably above that.
IVFFLAT_LISTS = 100


class GuidelineDocument(Base):
    __tablename__ = "guideline_documents"

    document_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    issuing_body: Mapped[str] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(Text)
    publication_year: Mapped[int | None] = mapped_column(SmallInteger)
    source_url: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)

    chunks: Mapped[list[GuidelineChunk]] = relationship(back_populates="document")

    __table_args__ = (
        UniqueConstraint("title", "issuing_body", name="uq_guideline_documents_natural"),
    )


class GuidelineChunk(Base):
    __tablename__ = "guideline_chunks"

    chunk_id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("guideline_documents.document_id")
    )
    section: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))

    document: Mapped[GuidelineDocument] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_guideline_chunks_natural"
        ),
        # Approximate-nearest-neighbour index for retrieval. Declared on the model
        # rather than only in the migration: an index that exists in the database
        # but not in the metadata is one that the next `alembic revision
        # --autogenerate` will helpfully offer to drop.
        Index(
            "idx_guideline_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"lists": IVFFLAT_LISTS},
        ),
    )
