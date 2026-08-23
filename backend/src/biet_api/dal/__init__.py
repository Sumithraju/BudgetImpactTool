"""Data access layer: engine and session lifecycle. Owns no domain logic."""

from .session import engine, session_scope, session_factory

__all__ = ["engine", "session_factory", "session_scope"]
