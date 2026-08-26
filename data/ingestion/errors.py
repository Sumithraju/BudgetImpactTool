"""Ingestion exception hierarchy.

Mirrors the pattern in the `biet-backend` skill, section 8.1: every error carries
its own code, and adding a new one means adding a subclass.
"""

from __future__ import annotations

from typing import Any, ClassVar


class IngestionError(Exception):
    """Base for every ingestion failure."""

    code: ClassVar[str] = "INGESTION_ERROR"

    def __init__(self, message: str | None = None, **context: Any) -> None:
        self.message = message or self.__class__.__doc__ or self.code
        self.context = context
        super().__init__(self.message)


class SourceFetchError(IngestionError):
    """The source could not be retrieved."""

    code = "SOURCE_FETCH_FAILED"


class SourceValidationError(IngestionError):
    """The retrieved payload failed validation and was not published."""

    code = "SOURCE_VALIDATION_FAILED"


class MissingValueError(SourceValidationError):
    """A required value is absent for every available year."""

    code = "MISSING_VALUE"


class CoverageError(SourceValidationError):
    """The payload does not cover every target market."""

    code = "INCOMPLETE_COVERAGE"
