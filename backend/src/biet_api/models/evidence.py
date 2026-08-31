"""EviTrack evidence records."""

from __future__ import annotations

from sqlalchemy import Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EvidenceRecord(Base):
    """One evidence item discovered from an external source."""

    __tablename__ = "evidence_records"

    evidence_id: Mapped[int] = mapped_column(primary_key=True)

    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)


Index(
    "uq_evidence_records_source_source_id",
    EvidenceRecord.source,
    EvidenceRecord.source_id,
    unique=True,
    postgresql_where=EvidenceRecord.source_id.is_not(None),
)
