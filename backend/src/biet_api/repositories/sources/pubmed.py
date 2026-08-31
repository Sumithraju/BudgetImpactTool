"""PubMed evidence source for EviTrack."""

from __future__ import annotations

import httpx

from ...schemas.evidence import EvidenceResult


PUBMED_EUTILS_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedSource:
    """Retrieve scientific evidence from PubMed."""

    name = "PubMed"

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def _get_with_retry(
        self,
        url: str,
        *,
        params: dict[str, object],
        attempts: int = 3,
    ) -> httpx.Response:
        """GET an upstream URL with bounded retries for transient failures."""
        for attempt in range(attempts):
            try:
                response = self._client.get(
                    url,
                    params=params,
                )

                if response.status_code not in {502, 503, 504}:
                    response.raise_for_status()
                    return response

                if attempt == attempts - 1:
                    response.raise_for_status()

            except httpx.ConnectError:
                if attempt == attempts - 1:
                    raise

        raise RuntimeError("Retry loop exited unexpectedly")

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[EvidenceResult]:
        """Search PubMed and return normalized evidence records."""

        response = self._get_with_retry(
            f"{PUBMED_EUTILS_URL}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmax": limit,
                "retmode": "json",
                "sort": "relevance",
            },
        )

        payload = response.json()

        search_result = payload.get("esearchresult", {})
        ids = search_result.get("idlist", [])

        if not ids:
            return []

        details = self._get_with_retry(
            f"{PUBMED_EUTILS_URL}/esummary.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "json",
            },
        )

        result = details.json().get("result", {})

        evidence: list[EvidenceResult] = []

        for rank, pmid in enumerate(ids):
            record = result.get(pmid)

            if not isinstance(record, dict):
                continue

            title = str(record.get("title") or "").strip()

            if not title:
                continue

            pubdate = str(record.get("pubdate") or "").strip()

            year: int | None = None

            if pubdate[:4].isdigit():
                year = int(pubdate[:4])

            authors = [
                str(author.get("name"))
                for author in record.get("authors", [])
                if isinstance(author, dict)
                and author.get("name")
            ]

            article_ids = record.get("articleids") or []

            doi: str | None = None

            for article_id in article_ids:
                if (
                    isinstance(article_id, dict)
                    and article_id.get("idtype") == "doi"
                    and article_id.get("value")
                ):
                    doi = str(article_id["value"])
                    break

            evidence.append(
                EvidenceResult(
                    title=title,
                    source=self.name,
                    source_id=str(pmid),
                    year=year,
                    authors=authors,
                    abstract=None,
                    doi=doi,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    evidence_type="research_article",
                    relevance=max(
                        0.0,
                        1.0 - (rank / max(len(ids), 1)),
                    ),
                )
            )

        return evidence
