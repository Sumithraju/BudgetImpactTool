"""Generic upsert-by-natural-key.

Publish is transactional and superseding, never deleting (M0 section 5.7): a
second publish with the same natural key updates the row in place rather than
inserting a duplicate or leaving the old row behind.
"""

from __future__ import annotations

from typing import Any, TypeVar

from biet_api.models.base import Base
from sqlalchemy import select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT", bound=Base)


def upsert(
    session: Session,
    model: type[ModelT],
    natural_key: dict[str, Any],
    values: dict[str, Any],
) -> ModelT:
    """Insert or update one row of `model`, keyed on `natural_key`."""
    row = session.execute(
        select(model).filter_by(**natural_key)
    ).scalar_one_or_none()

    if row is None:
        row = model(**natural_key, **values)
        session.add(row)
    else:
        for column, value in values.items():
            setattr(row, column, value)
    return row
