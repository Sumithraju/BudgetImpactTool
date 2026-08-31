"""Offline tests for EviTrack external evidence retrieval.

These tests use httpx.MockTransport so no live PubMed request and no
PostgreSQL connection are required.

EviTrack is intentionally tested in isolation from the deterministic BIA
engine and the existing guideline retrieval system.
"""

from __future__ import annotations

import httpx

from biet_api.repositories.evidence import EvidenceRepository


def test_pubmed_search_normalizes_results() -> None:
    """PubMed search results are converted into EvidenceResult objects."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/esearch.fcgi"):
            return httpx.Response(
                200,
                json={
                    "esearchresult": {
                        "idlist": ["12345678"],
                    }
                },
            )

        if request.url.path.endswith("/esummary.fcgi"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "12345678": {
                            "title": "Arthritis prevalence in adults",
                            "pubdate": "2025 Jan",
                            "authors": [
                                {"name": "Author One"},
                                {"name": "Author Two"},
                            ],
                            "articleids": [
                                {
                                    "idtype": "doi",
                                    "value": "10.1000/example",
                                }
                            ],
                        }
                    }
                },
            )

        return httpx.Response(404)


    client = httpx.Client(transport=httpx.MockTransport(handler))
    repository = EvidenceRepository(client=client)

    try:
        results = repository.search_pubmed(
            "arthritis prevalence adults",
            limit=10,
        )
    finally:
        repository.close()
        client.close()

    assert len(results) == 1

    result = results[0]

    assert result.title == "Arthritis prevalence in adults"
    assert result.source == "PubMed"
    assert result.source_id == "12345678"
    assert result.year == 2025
    assert result.authors == ["Author One", "Author Two"]
    assert result.doi == "10.1000/example"
    assert result.url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert result.evidence_type == "research_article"
    assert result.abstract is None
    assert result.relevance == 1.0


def test_pubmed_search_returns_empty_when_no_ids_are_found() -> None:
    """A valid search with no PubMed matches returns an empty list."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/esearch.fcgi")

        return httpx.Response(
            200,
            json={
                "esearchresult": {
                    "idlist": [],
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repository = EvidenceRepository(client=client)

    try:
        results = repository.search_pubmed(
            "query with no matching records",
            limit=10,
        )
    finally:
        repository.close()
        client.close()

    assert results == []


def test_pubmed_search_skips_records_without_titles() -> None:
    """Malformed/incomplete PubMed records do not become evidence results."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/esearch.fcgi"):
            return httpx.Response(
                200,
                json={
                    "esearchresult": {
                        "idlist": ["111", "222"],
                    }
                },
            )

        if request.url.path.endswith("/esummary.fcgi"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "111": {
                            "title": "",
                            "pubdate": "2024",
                            "authors": [],
                            "articleids": [],
                        },
                        "222": {
                            "title": "Valid evidence record",
                            "pubdate": "2024",
                            "authors": [],
                            "articleids": [],
                        },
                    }
                },
            )

        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repository = EvidenceRepository(client=client)

    try:
        results = repository.search_pubmed(
            "test query",
            limit=10,
        )
    finally:
        repository.close()
        client.close()

    assert len(results) == 1
    assert results[0].source_id == "222"
    assert results[0].title == "Valid evidence record"


def test_pubmed_search_retries_transient_upstream_failure() -> None:
    """A transient 503 is retried before the failure is surfaced."""

    calls = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1

        if request.url.path.endswith("/esearch.fcgi"):
            if calls[0] == 1:
                return httpx.Response(503)

            return httpx.Response(
                200,
                json={
                    "esearchresult": {
                        "idlist": [],
                    }
                },
            )

        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repository = EvidenceRepository(client=client)

    try:
        results = repository.search_pubmed("arthritis prevalence")
    finally:
        repository.close()
        client.close()

    assert results == []
    assert calls[0] == 2


def test_pubmed_search_retries_connection_error() -> None:
    """A transient connection failure is retried."""

    calls = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1

        if calls[0] == 1:
            raise httpx.ConnectError("connection reset", request=request)

        if request.url.path.endswith("/esearch.fcgi"):
            return httpx.Response(
                200,
                json={
                    "esearchresult": {
                        "idlist": [],
                    }
                },
            )

        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repository = EvidenceRepository(client=client)

    try:
        results = repository.search_pubmed("arthritis prevalence")
    finally:
        repository.close()
        client.close()

    assert results == []
    assert calls[0] == 2


def test_pubmed_search_bounds_transient_retries() -> None:
    """A persistent transient failure is eventually surfaced."""

    calls = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repository = EvidenceRepository(client=client)

    try:
        try:
            repository.search_pubmed("arthritis prevalence")
        except httpx.HTTPStatusError as exc:
            assert exc.response.status_code == 503
        else:
            raise AssertionError("Expected HTTPStatusError")
    finally:
        repository.close()
        client.close()

    assert calls[0] == 3


def test_pubmed_search_does_not_retry_non_transient_client_error() -> None:
    """A non-retryable 400 is returned immediately."""

    calls = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        return httpx.Response(400)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    repository = EvidenceRepository(client=client)

    try:
        try:
            repository.search_pubmed("invalid request")
        except httpx.HTTPStatusError as exc:
            assert exc.response.status_code == 400
        else:
            raise AssertionError("Expected HTTPStatusError")
    finally:
        repository.close()
        client.close()

    assert calls[0] == 1

def test_save_creates_new_evidence_record() -> None:
    """A new evidence item is persisted and reported as newly created."""
    from biet_api.dal.session import session_factory
    from biet_api.models import EvidenceRecord
    from biet_api.schemas.evidence import EvidenceResult

    evidence = EvidenceResult(
        title="Test evidence",
        source="PubMed",
        source_id="TEST-NEW-001",
        year=2025,
        authors=["Test Author"],
        abstract=None,
        doi="10.1000/test-new-001",
        url="https://pubmed.ncbi.nlm.nih.gov/TEST-NEW-001/",
        evidence_type="research_article",
        relevance=1.0,
    )

    # Ensure the test starts from a clean state.
    with session_factory() as session:
        session.query(EvidenceRecord).filter(
            EvidenceRecord.source == "PubMed",
            EvidenceRecord.source_id == "TEST-NEW-001",
        ).delete(synchronize_session=False)
        session.commit()

    repository = EvidenceRepository()

    try:
        evidence_id, created = repository.save(evidence)
    finally:
        repository.close()

    try:
        assert created is True
        assert evidence_id > 0

        with session_factory() as session:
            record = session.get(EvidenceRecord, evidence_id)
            assert record is not None
            assert record.source == "PubMed"
            assert record.source_id == "TEST-NEW-001"
    finally:
        # Do not leave test evidence in the real development database.
        with session_factory() as session:
            session.query(EvidenceRecord).filter(
                EvidenceRecord.source == "PubMed",
                EvidenceRecord.source_id == "TEST-NEW-001",
            ).delete(synchronize_session=False)
            session.commit()

def test_save_returns_existing_record_without_duplicate() -> None:
    """Saving the same source/source_id returns the existing record."""
    from biet_api.dal.session import session_factory
    from biet_api.models import EvidenceRecord
    from biet_api.schemas.evidence import EvidenceResult

    evidence = EvidenceResult(
        title="Test duplicate evidence",
        source="PubMed",
        source_id="TEST-DUP-001",
        year=2025,
        authors=["Test Author"],
        abstract=None,
        doi="10.1000/test-dup-001",
        url="https://pubmed.ncbi.nlm.nih.gov/TEST-DUP-001/",
        evidence_type="research_article",
        relevance=1.0,
    )

    # Ensure the test starts from a clean state.
    with session_factory() as session:
        session.query(EvidenceRecord).filter(
            EvidenceRecord.source == "PubMed",
            EvidenceRecord.source_id == "TEST-DUP-001",
        ).delete(synchronize_session=False)
        session.commit()

    repository = EvidenceRepository()

    try:
        first_id, first_created = repository.save(evidence)
        second_id, second_created = repository.save(evidence)
    finally:
        repository.close()

    try:
        assert first_created is True
        assert second_created is False
        assert second_id == first_id

        with session_factory() as session:
            records = session.query(EvidenceRecord).filter(
                EvidenceRecord.source == "PubMed",
                EvidenceRecord.source_id == "TEST-DUP-001",
            ).all()

            assert len(records) == 1
    finally:
        # Do not leave test evidence in the real development database.
        with session_factory() as session:
            session.query(EvidenceRecord).filter(
                EvidenceRecord.source == "PubMed",
                EvidenceRecord.source_id == "TEST-DUP-001",
            ).delete(synchronize_session=False)
            session.commit()


def test_add_evidence_returns_scalar_evidence_id() -> None:
    """POST /evidence returns the saved evidence ID, not the repository tuple."""
    from fastapi.testclient import TestClient

    from biet_api.main import app

    payload = {
        "title": "API EviTrack test",
        "source": "PubMed",
        "source_id": "API-TEST-001",
        "year": 2025,
        "authors": ["API Test Author"],
        "abstract": None,
        "doi": "10.1000/api-test-001",
        "url": "https://pubmed.ncbi.nlm.nih.gov/API-TEST-001/",
        "evidence_type": "research_article",
        "relevance": 1.0,
    }

    client = TestClient(app)

    try:
        response = client.post(
            "/api/v1/evitrack/evidence",
            json=payload,
        )

        assert response.status_code == 200

        body = response.json()

        assert body["status"] == "saved"
        assert isinstance(body["evidence_id"], int)
        assert body["evidence_id"] > 0
        assert body["evidence"]["source_id"] == "API-TEST-001"
    finally:
        from biet_api.dal.session import session_factory
        from biet_api.models import EvidenceRecord

        with session_factory() as session:
            session.query(EvidenceRecord).filter(
                EvidenceRecord.source == "PubMed",
                EvidenceRecord.source_id == "API-TEST-001",
            ).delete(synchronize_session=False)
            session.commit()

def test_search_endpoint_reports_new_and_existing_counts(monkeypatch) -> None:
    """GET /search returns normalized results and correct persistence counts."""
    from fastapi.testclient import TestClient

    from biet_api.main import app
    from biet_api.schemas.evidence import EvidenceResult

    results = [
        EvidenceResult(
            title="First API search evidence",
            source="PubMed",
            source_id="SEARCH-TEST-001",
            year=2025,
            authors=["Search Author One"],
            abstract=None,
            doi="10.1000/search-test-001",
            url="https://pubmed.ncbi.nlm.nih.gov/SEARCH-TEST-001/",
            evidence_type="research_article",
            relevance=1.0,
        ),
        EvidenceResult(
            title="Second API search evidence",
            source="PubMed",
            source_id="SEARCH-TEST-002",
            year=2024,
            authors=["Search Author Two"],
            abstract=None,
            doi="10.1000/search-test-002",
            url="https://pubmed.ncbi.nlm.nih.gov/SEARCH-TEST-002/",
            evidence_type="research_article",
            relevance=0.5,
        ),
    ]

    class FakeRepository:
        def __init__(self) -> None:
            self.saved = set()

        def search(
            self,
            query: str,
            *,
            source: str = "pubmed",
            limit: int = 10,
        ) -> list[EvidenceResult]:
            assert query == "arthritis"
            assert source == "pubmed"
            assert limit == 2
            return results

        def search_pubmed(
            self,
            query: str,
            *,
            limit: int = 10,
        ) -> list[EvidenceResult]:
            return self.search(
                query,
                source="pubmed",
                limit=limit,
            )

        def save(self, evidence: EvidenceResult) -> tuple[int, bool]:
            if evidence.source_id in self.saved:
                return 101, False

            self.saved.add(evidence.source_id)
            return 100 + len(self.saved), True

        def close(self) -> None:
            pass

    repository = FakeRepository()

    monkeypatch.setattr(
        "biet_api.routes.evitrack.EvidenceRepository",
        lambda: repository,
    )

    client = TestClient(app)

    response = client.get(
        "/api/v1/evitrack/search",
        params={
            "q": "arthritis",
            "limit": 2,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["query"] == "arthritis"
    assert body["source"] == "PubMed"
    assert body["saved_count"] == 2
    assert body["new_count"] == 2
    assert body["existing_count"] == 0
    assert len(body["results"]) == 2
    assert body["results"][0]["source_id"] == "SEARCH-TEST-001"
    assert body["results"][1]["source_id"] == "SEARCH-TEST-002"


def test_repository_generic_search_uses_registered_source() -> None:
    """Generic repository search dispatches through the source registry."""
    from biet_api.schemas.evidence import EvidenceResult

    class FakeSource:
        name = "fake"

        def search(
            self,
            query: str,
            *,
            limit: int = 10,
        ) -> list[EvidenceResult]:
            assert query == "test query"
            assert limit == 2

            return [
                EvidenceResult(
                    title="Generic search test",
                    source="Fake",
                    source_id="FAKE-001",
                    year=2025,
                    authors=["Test Author"],
                    abstract=None,
                    doi=None,
                    url="https://example.org/fake-001",
                    evidence_type="test",
                    relevance=1.0,
                )
            ]

    from biet_api.repositories.evidence import EvidenceRepository

    repository = EvidenceRepository()

    try:
        repository._source_registry.register(FakeSource())

        results = repository.search(
            "test query",
            source="fake",
            limit=2,
        )
    finally:
        repository.close()

    assert len(results) == 1
    assert results[0].source == "Fake"
    assert results[0].source_id == "FAKE-001"

def test_repository_registers_pubmed_source() -> None:
    """The repository registers PubMed as an available evidence source."""
    from biet_api.repositories.evidence import EvidenceRepository

    repository = EvidenceRepository()

    try:
        assert "pubmed" in repository._source_registry.names()
    finally:
        repository.close()

def test_sources_endpoint_lists_registered_sources() -> None:
    """GET /sources exposes the currently registered EviTrack sources."""
    from fastapi.testclient import TestClient

    from biet_api.main import app

    client = TestClient(app)

    response = client.get("/api/v1/evitrack/sources")

    assert response.status_code == 200

    body = response.json()

    assert "sources" in body
    assert {"name": "pubmed"} in body["sources"]


def test_search_endpoint_dispatches_requested_source(monkeypatch) -> None:
    """GET /search passes the requested source to the repository."""
    from fastapi.testclient import TestClient

    from biet_api.main import app
    from biet_api.schemas.evidence import EvidenceResult

    class FakeRepository:
        def __init__(self) -> None:
            self.requested_source = None

        def search(
            self,
            query: str,
            *,
            source: str = "pubmed",
            limit: int = 10,
        ) -> list[EvidenceResult]:
            self.requested_source = source

            assert query == "obesity"
            assert source == "fake"
            assert limit == 1

            return [
                EvidenceResult(
                    title="Fake evidence source result",
                    source="Fake",
                    source_id="FAKE-API-001",
                    year=2025,
                    authors=["Test Author"],
                    abstract=None,
                    doi=None,
                    url="https://example.org/fake-api-001",
                    evidence_type="test",
                    relevance=1.0,
                )
            ]

        def save(self, evidence: EvidenceResult) -> tuple[int, bool]:
            return 999, True

        def close(self) -> None:
            pass

    repository = FakeRepository()

    monkeypatch.setattr(
        "biet_api.routes.evitrack.EvidenceRepository",
        lambda: repository,
    )

    client = TestClient(app)

    response = client.get(
        "/api/v1/evitrack/search",
        params={
            "q": "obesity",
            "source": "fake",
            "limit": 1,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["query"] == "obesity"
    assert body["source"] == "Fake"
    assert body["saved_count"] == 1
    assert body["new_count"] == 1
    assert body["existing_count"] == 0
    assert body["results"][0]["source_id"] == "FAKE-API-001"
