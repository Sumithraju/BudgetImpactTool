"""Registry for EviTrack external evidence sources."""

from __future__ import annotations

from .base import EvidenceSource


class EvidenceSourceRegistry:
    """Register and retrieve evidence sources by stable name."""

    def __init__(self) -> None:
        self._sources: dict[str, EvidenceSource] = {}

    def register(self, source: EvidenceSource) -> None:
        """Register one evidence source."""
        name = source.name.strip().lower()

        if not name:
            raise ValueError("Evidence source name cannot be empty")

        if name in self._sources:
            raise ValueError(
                f"Evidence source already registered: {name}"
            )

        self._sources[name] = source

    def get(self, name: str) -> EvidenceSource:
        """Return a registered evidence source."""
        key = name.strip().lower()

        try:
            return self._sources[key]
        except KeyError as exc:
            raise KeyError(
                f"Evidence source not registered: {name}"
            ) from exc

    def names(self) -> list[str]:
        """Return registered source names."""
        return sorted(self._sources)
