"""HTTP client with retry, backoff and optional proxy support."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .config import settings
from .errors import SourceFetchError

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def _client() -> httpx.Client:
    kwargs: dict[str, Any] = {
        "timeout": settings.request_timeout_s,
        "follow_redirects": True,
        "headers": {"User-Agent": "BIET-ingestion/1.0"},
    }
    if settings.proxies:
        kwargs["proxy"] = settings.proxies
    return httpx.Client(**kwargs)


def get(url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    """GET with bounded retry on transient failures.

    Raises:
        SourceFetchError: after the configured number of attempts, or immediately
            on a non-retryable status such as 404.
    """
    last: Exception | None = None

    for attempt in range(1, settings.request_retries + 1):
        try:
            with _client() as client:
                response = client.get(url, params=params)

            if response.status_code in _RETRYABLE_STATUS:
                last = SourceFetchError(
                    f"retryable status {response.status_code}", url=url
                )
                log.warning(
                    "http_retryable", extra={"url": url, "status": response.status_code,
                                             "attempt": attempt}
                )
            elif response.is_error:
                # 404 and friends will not improve with another attempt.
                raise SourceFetchError(
                    f"HTTP {response.status_code}", url=url,
                    status=response.status_code,
                )
            else:
                return response

        except httpx.TimeoutException as exc:
            last = exc
            log.warning("http_timeout", extra={"url": url, "attempt": attempt})
        except httpx.TransportError as exc:
            last = exc
            log.warning("http_transport_error", extra={"url": url, "attempt": attempt})

        if attempt < settings.request_retries:
            time.sleep(settings.request_backoff_s * attempt)

    raise SourceFetchError(
        f"failed after {settings.request_retries} attempts: {last}", url=url
    )


def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    response = get(url, params)
    try:
        return response.json()
    except ValueError as exc:
        raise SourceFetchError(f"response was not valid JSON: {exc}", url=url) from exc
