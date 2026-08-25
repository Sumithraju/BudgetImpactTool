"""Generic upsert-by-natural-key.

Publish is transactional and superseding, never deleting (M0 section 5.7): a
second publish with the same natural key updates the row in place rather than
inserting a duplicate or leaving the old row behind.
"""

from __future__ import annotations

from typing import Any, TypeVar

from biet_api.models.base import Base
from sqlalchemy import select, text
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


def resync_sequence(session: Session, table: str, pk_column: str) -> None:
    """Advance a serial sequence past the highest id in its table.

    Most seed files let the sequence assign ids. Two — `drugs.csv` and
    `indications.csv` — carry their own primary keys, because the price and
    regimen files reference `drug_id` and the epidemiology file references
    `indication_id`, and a stable key is what lets those files be edited
    independently.

    Inserting with an explicit id does not advance the sequence, so the first
    row the *application* ever inserts collides with a seeded one. That fails
    at the point of the write with a duplicate-key error naming a primary key
    the caller never supplied, which is about as far from its cause as an
    error can get. Resyncing here keeps the seed pipeline's convenience
    without leaving that trap behind it.

    Raw SQL: `setval` and `pg_get_serial_sequence` have no ORM expression.
    The three-argument form handles the empty table — `setval(seq, 1, false)`
    makes the next value 1 rather than 2.
    """
    session.execute(
        text(
            f"SELECT setval("
            f"  pg_get_serial_sequence(:table, :column),"
            f"  COALESCE((SELECT MAX({pk_column}) FROM {table}), 1),"
            f"  COALESCE((SELECT MAX({pk_column}) FROM {table}), 0) > 0"
            f")"
        ),
        {"table": table, "column": pk_column},
    )
