"""Staging — the `stage` step of the pipeline in ARCHITECTURE.md section 7.4.

Raw payloads are written to `data/raw/` unmodified, which is the first half of
the audit trail. This table is the second half: it holds the *normalised* rows a
source produced, keyed by source, so a published value can be traced back to the
exact extract that produced it without re-reading a 124 MB CSV.

Normalised rather than raw on purpose. Storing the full NADAC extract would put
1.5 million rows in the database to support 1,200 published ones; the fetchers
already filter to the therapy classes in scope before this point.

ARCHITECTURE.md section 8 does not specify a staging schema, only that the stage
exists. One generic table is used rather than eight source-shaped ones.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StagingExtract(Base):
    __tablename__ = "staging_extracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(Text)
    row_index: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("source_id", "row_index", name="uq_staging_extracts_natural"),
        Index("idx_staging_extracts_source", "source_id", "fetched_at"),
    )
