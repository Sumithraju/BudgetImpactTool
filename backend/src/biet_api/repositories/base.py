"""Base repository — biet-backend skill section 2.

One repository per aggregate. Repositories own queries; services own
decisions. A repository never commits: transactions belong to the service
that opened them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ..models.base import Base


class BaseRepository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, pk: Any) -> ModelT | None:
        return self._session.get(self.model, pk)

    def add(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        return entity

    def list(self, *criteria: ColumnElement[bool]) -> Sequence[ModelT]:
        return self._session.scalars(select(self.model).where(*criteria)).all()
