"""API schemas for external EviTrack evidence discovery."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceResult(BaseModel):
    """One external evidence source returned by EviTrack."""

    title: str
    source: str
    source_id: str | None = None
    year: int | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    doi: str | None = None
    url: str
    evidence_type: str
    relevance: float | None = Field(default=None, ge=0.0, le=1.0)


class EvidenceDiscoveryResponse(BaseModel):
    """Normalized response from external evidence discovery."""

    query: str
    results: list[EvidenceResult] = Field(default_factory=list)
