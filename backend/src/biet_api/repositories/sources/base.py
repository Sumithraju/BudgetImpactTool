"""Common interface for EviTrack evidence sources."""

from __future__ import annotations

from typing import Protocol

from ...schemas.evidence import EvidenceResult


class EvidenceSource(Protocol):
    """Interface implemented by every external EviTrack evidence source."""

    name: str

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[EvidenceResult]:
        """Search the external source and return normalized evidence."""
        ...
