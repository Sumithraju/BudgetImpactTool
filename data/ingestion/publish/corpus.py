"""Guideline corpus embedding — M0 acceptance criterion: "guideline_chunks —
corpus embedded, ivfflat index built."

PDFs under `data/corpus/` are chunked and embedded with a local sentence
embedding model (fastembed — no API key, no proxy). The ivfflat index itself
is schema, created by the Alembic migration; this module only populates rows.
Retrieval (the pgvector `<=>` similarity query) is a repository concern for a
later phase, not ingestion.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from biet_api.dal import session_scope
from biet_api.models import GuidelineChunk, GuidelineDocument
from fastembed import TextEmbedding
from pypdf import PdfReader

from ..config import settings
from .upsert import upsert

log = logging.getLogger(__name__)

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
MIN_CHUNK_CHARS = 100


@dataclass(frozen=True)
class DocumentMeta:
    filename: str
    title: str
    issuing_body: str
    document_type: str
    publication_year: int | None
    source_url: str | None


DOCUMENTS: tuple[DocumentMeta, ...] = (
    DocumentMeta(
        filename="PIIS1098301510604718.pdf",
        title="Principles of Good Practice for Budget Impact Analysis: Report of the "
              "ISPOR Task Force on Good Research Practices—Budget Impact Analysis",
        issuing_body="ISPOR",
        document_type="task_force_report",
        publication_year=2007,
        source_url="https://doi.org/10.1111/j.1524-4733.2007.00187.x",
    ),
    DocumentMeta(
        filename="Budget Impact Analysis—Principles of Good Practice_ Report of "
                 "the ISPOR 2012 Budget Impact Analysis Good Practice II Task Force "
                 "- PIIS1098301513042356.pdf",
        title="Budget Impact Analysis—Principles of Good Practice: Report of the "
              "ISPOR 2012 Budget Impact Analysis Good Practice II Task Force",
        issuing_body="ISPOR",
        document_type="task_force_report",
        publication_year=2014,
        source_url="https://doi.org/10.1016/j.jval.2013.08.2291",
    ),
    DocumentMeta(
        filename="ispor_bia_editorial_2014.pdf",
        title="Review: Report of the ISPOR 2012 Budget Impact Analysis Good Practice "
              "II Task Force",
        issuing_body="ISPOR",
        document_type="editorial",
        publication_year=2014,
        source_url=None,
    ),
    DocumentMeta(
        filename="nice_budget_impact_test_procedure.pdf",
        title="Procedure: Budget Impact Test and Varying the Timescale for Mandatory "
              "Funding",
        issuing_body="NICE",
        document_type="procedure",
        publication_year=None,
        source_url="https://www.nice.org.uk/",
    ),
    DocumentMeta(
        filename="who_bia_teaching_slides.pdf",
        title="Introduction to Budget Impact Analysis",
        issuing_body="WHO",
        document_type="teaching_slides",
        publication_year=2021,
        source_url=None,
    ),
)


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    return text.strip()


def _extract_pages(path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(path)
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = _clean(page.extract_text() or "")
        if len(text) > 50:
            pages.append((index, text))
    return pages


def _chunk(text: str) -> list[str]:
    """Fixed-size sliding window over characters, on whitespace boundaries.

    A hand-rolled splitter rather than a text-splitting library: the corpus is
    five documents, and chunking correctness here only needs "roughly
    paragraph sized with some overlap" — not enough to justify a dependency.
    """
    if len(text) <= CHUNK_SIZE:
        return [text] if len(text) >= MIN_CHUNK_CHARS else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if len(piece) >= MIN_CHUNK_CHARS:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def ingest_corpus() -> dict[str, int]:
    """Chunk, embed and publish every document in `DOCUMENTS`.

    Idempotent: re-running re-embeds and upserts on (document, chunk_index),
    superseding prior chunks for that document rather than duplicating them.
    """
    model = TextEmbedding(model_name=EMBEDDING_MODEL)
    counts: dict[str, int] = {}

    for meta in DOCUMENTS:
        path = settings.corpus_dir / meta.filename
        if not path.exists():
            log.warning("corpus_missing", extra={"file": meta.filename})
            continue

        pages = _extract_pages(path)
        records: list[tuple[int, int, str]] = []        # (chunk_index, page_number, text)
        index = 0
        for page_number, text in pages:
            for piece in _chunk(text):
                records.append((index, page_number, piece))
                index += 1

        if not records:
            log.warning("corpus_empty", extra={"file": meta.filename})
            continue

        embeddings = list(model.embed([r[2] for r in records]))

        with session_scope() as session:
            document = upsert(
                session, GuidelineDocument,
                natural_key={"title": meta.title, "issuing_body": meta.issuing_body},
                values={
                    "document_type": meta.document_type,
                    "publication_year": meta.publication_year,
                    "source_url": meta.source_url,
                    "file_path": f"data/corpus/{meta.filename}",
                },
            )
            session.flush()           # need document.document_id for the FK below

            for (chunk_index, page_number, text), embedding in zip(records, embeddings):
                upsert(
                    session, GuidelineChunk,
                    natural_key={"document_id": document.document_id,
                                 "chunk_index": chunk_index},
                    values={
                        "section": None,
                        "page_number": page_number,
                        "chunk_text": text,
                        "embedding": embedding.tolist(),
                    },
                )

        counts[meta.filename] = len(records)
        log.info("corpus_ingested", extra={"file": meta.filename, "chunks": len(records)})

    return counts
