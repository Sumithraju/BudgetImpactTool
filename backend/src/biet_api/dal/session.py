"""Engine and session lifecycle.

Transactions belong to callers, not to repositories. `session_scope` is the unit
of work: it commits on clean exit and rolls back on any exception, which is what
makes a failed source leave previously published data intact (M0 section 5.7).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings

engine: Engine = create_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_pre_ping=True,
    future=True,
)

session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency. Rolls back and closes on the way out.

    Deliberately does *not* commit: routes commit explicitly after a
    successful write, so a handler that raises never leaves a partial
    transaction committed behind it.
    """
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
