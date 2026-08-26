"""Transient-failure handling in comparator retrieval.

The behaviour under test is the one a user reported as "We could not reach
the drug database to look up GLP1R". The endpoint was healthy; a single
transient failure on the way to it was being turned straight into an error
and the reader was asked to retry by hand. These tests pin down that the
retry now happens in the repository, and — just as important — that it does
not happen for failures a retry cannot fix, which would otherwise turn one
fast, accurate error into three slow ones.

Driven through `httpx.MockTransport` rather than a live endpoint, so the
suite stays offline and a scripted sequence of failures is exactly
reproducible.
"""

from __future__ import annotations

import httpx
import pytest

from biet_api.repositories.comparator import (
    ComparatorRepository,
    SchemaRejectedError,
    UnknownTargetError,
)

_HIT = {
    "data": {
        "search": {
            "hits": [{"id": "ENSG00000112164", "name": "GLP1R", "entity": "target"}],
        },
    },
}


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """The backoff is real time; nothing here needs to spend it."""
    monkeypatch.setattr("biet_api.repositories.comparator.time.sleep", lambda _: None)


def _repo(*responses: object) -> tuple[ComparatorRepository, list[int]]:
    """A repository whose transport replays `responses`, and an attempt counter.

    Each entry is either an exception to raise or an `httpx.Response` to
    return. The last entry repeats, so a test only scripts the prefix it
    cares about.
    """
    calls = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        index = min(calls[0], len(responses) - 1)
        calls[0] += 1
        outcome = responses[index]
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, httpx.Response)
        return outcome

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ComparatorRepository(client=client), calls


# --------------------------------------------------------------- retried

def test_a_single_connection_reset_is_retried_not_reported() -> None:
    """The reported failure, in miniature: one blip, then a healthy endpoint."""
    repo, calls = _repo(
        httpx.ConnectError("connection reset"),
        httpx.Response(200, json=_HIT),
    )

    ensembl_id, symbol = repo.resolve_target("GLP1R")

    assert (ensembl_id, symbol) == ("ENSG00000112164", "GLP1R")
    assert calls[0] == 2, "the first attempt failed and the second succeeded"


def test_a_read_timeout_is_retried() -> None:
    repo, calls = _repo(
        httpx.ReadTimeout("timed out"),
        httpx.Response(200, json=_HIT),
    )

    assert repo.resolve_target("GLP1R")[1] == "GLP1R"
    assert calls[0] == 2


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_server_side_statuses_are_retried(status: int) -> None:
    repo, calls = _repo(
        httpx.Response(status),
        httpx.Response(200, json=_HIT),
    )

    assert repo.resolve_target("GLP1R")[1] == "GLP1R"
    assert calls[0] == 2


def test_retries_are_bounded_and_the_failure_still_surfaces() -> None:
    """Retrying is not the same as hanging on. A genuine outage still errors."""
    repo, calls = _repo(httpx.ConnectError("down"))

    with pytest.raises(httpx.ConnectError):
        repo.resolve_target("GLP1R")

    assert calls[0] == 3, "bounded at DISCOVERY_RETRY_ATTEMPTS"


# ----------------------------------------------------------- not retried

def test_a_refused_query_is_not_retried_and_is_not_called_an_outage() -> None:
    """A GraphQL rejection is a 200 with an `errors` array.

    The query was refused, not lost. Repeating it three times would have it
    refused three times, and reporting it as a temporary outage sends the
    reader looking for a network problem that does not exist.
    """
    repo, calls = _repo(
        httpx.Response(200, json={"errors": [{"message": "Cannot query 'knownDrugs'"}]}),
    )

    with pytest.raises(SchemaRejectedError, match="knownDrugs"):
        repo.resolve_target("GLP1R")

    assert calls[0] == 1, "a refusal is final on the first answer"


def test_a_client_error_is_not_retried() -> None:
    """A 400 is a statement about the request; it reads the same every time."""
    repo, calls = _repo(httpx.Response(400))

    with pytest.raises(httpx.HTTPStatusError):
        repo.resolve_target("GLP1R")

    assert calls[0] == 1


def test_an_unmatched_symbol_still_fails_fast() -> None:
    """A typo must not spend three round trips before being told it is a typo."""
    repo, calls = _repo(httpx.Response(200, json={"data": {"search": {"hits": []}}}))

    with pytest.raises(UnknownTargetError):
        repo.resolve_target("NOTAGENE9Z")

    assert calls[0] == 1


def test_reactome_404_means_not_annotated_and_is_answered_at_once() -> None:
    """404 here is Reactome's way of saying "no pathways", not a failure."""
    repo, calls = _repo(httpx.Response(404, json={}))

    assert repo.reactome_pathways("P43220") == ()
    assert calls[0] == 1, "an ordinary empty answer costs one round trip"


def test_reactome_recovers_from_a_transient_failure_too() -> None:
    repo, calls = _repo(
        httpx.Response(503),
        httpx.Response(200, json=[{"stId": "R-HSA-420092"}]),
    )

    assert repo.reactome_pathways("P43220") == ("R-HSA-420092",)
    assert calls[0] == 2


# ------------------------------------------------------------------ proxies

def test_the_shared_client_still_honours_an_environment_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A regression guard with a specific mistake in mind.

    httpx only reads HTTP_PROXY/HTTPS_PROXY/NO_PROXY when it constructs the
    transport itself — internally, `allow_env_proxies = trust_env and
    transport is None`. Passing an explicit transport (for its connect-level
    retries, say) silently disables proxy support for every deployment behind
    one, which is precisely where "we could not reach the drug database" is
    most likely to be seen. Retry belongs in `_send` for that reason.
    """
    import biet_api.repositories.comparator as module

    monkeypatch.setattr(module, "_shared", None)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")

    client = module._shared_client()

    assert any(v is not None for v in client._mounts.values()), (
        "an environment proxy must still reach the transport"
    )


def test_the_client_is_shared_so_connections_are_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One client per process, not one per request.

    A client per request meant a fresh TLS handshake to a remote public API on
    every discovery — the most likely origin of the transient connect error.
    """
    import biet_api.repositories.comparator as module

    monkeypatch.setattr(module, "_shared", None)

    assert ComparatorRepository()._client is ComparatorRepository()._client


def test_an_injected_client_still_wins() -> None:
    """Tests and callers must keep being able to supply their own."""
    own = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert ComparatorRepository(client=own)._client is own
