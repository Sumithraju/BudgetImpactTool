"""Data access layer: engine and session lifecycle. Owns no domain logic."""

from .session import engine, get_session, session_factory, session_scope

__all__ = ["engine", "get_session", "session_factory", "session_scope"]
