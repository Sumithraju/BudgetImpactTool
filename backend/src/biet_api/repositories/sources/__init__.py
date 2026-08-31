"""External evidence source implementations."""

from .base import EvidenceSource
from .pubmed import PubMedSource

__all__ = [
    "EvidenceSource",
    "PubMedSource",
]
