"""Fetcher contract shared by every source.

Pipeline stages, per M0 section 5.7:

    extract -> validate -> normalise -> stage -> transform -> publish

`extract` writes the raw payload to disk unmodified so the audit trail from a
published value back to its source payload is preserved. `transform` is pure with
respect to the network: it reads only from the file `extract` produced, which is
what lets the tests run offline.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, ConfigDict

from .config import settings
from .constants import SourceId

log = logging.getLogger(__name__)


class SourceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: SourceId
    rows_fetched: int
    rows_published: int
    fetched_at: datetime
    warnings: tuple[str, ...] = ()
    ok: bool = True


class Fetcher(ABC):
    """One implementation per external source."""

    source_id: SourceId

    @property
    def raw_path(self) -> Path:
        return settings.raw_dir / f"{self.source_id.value}.json"

    @abstractmethod
    def extract(self) -> Path:
        """Retrieve the payload and write it to `raw_path`. Returns that path."""

    @abstractmethod
    def validate(self, raw: Path) -> None:
        """Raise SourceValidationError if the payload is unusable."""

    @abstractmethod
    def transform(self, raw: Path) -> pd.DataFrame:
        """Normalise into the published shape. No network access."""

    def run(self, *, extract: bool = True) -> tuple[pd.DataFrame, SourceResult]:
        """Extract (optionally), validate and transform. Publishing is separate."""
        raw = self.extract() if extract else self.raw_path
        if not raw.exists():
            raise FileNotFoundError(
                f"{raw} not present; run with extract=True first"
            )

        self.validate(raw)
        frame = self.transform(raw)

        log.info(
            "source_transformed",
            extra={"source": self.source_id.value, "rows": len(frame)},
        )
        return frame, SourceResult(
            source_id=self.source_id,
            rows_fetched=len(frame),
            rows_published=0,          # set by the publish stage
            fetched_at=datetime.now(UTC),
        )
