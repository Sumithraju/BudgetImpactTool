"""Shared fixtures, and a standing guarantee that tests never touch the network.

M0 section 10 requires the ingestion suite to run offline. Rather than trusting
that by convention, the autouse fixture below makes any socket use a hard failure,
so a test that reaches for a live endpoint fails loudly instead of passing slowly
and flaking in CI.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that attempts a network connection."""

    def blocked(*args: object, **kwargs: object) -> None:
        raise RuntimeError(
            "network access attempted during tests; use a fixture instead"
        )

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
