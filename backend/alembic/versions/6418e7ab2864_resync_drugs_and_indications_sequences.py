"""resync drugs and indications sequences

Revision ID: 6418e7ab2864
Revises: d07438e081b4
Create Date: 2026-08-25 14:57:16.943995
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = '6418e7ab2864'
down_revision: str | None = 'd07438e081b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Advance both sequences past the ids the seed files supplied.

    `drugs.csv` and `indications.csv` carry their own primary keys so that
    the price, regimen and epidemiology files can reference them stably. An
    insert with an explicit id does not advance the sequence, so the first
    row the application inserts — the first comparator promoted under M12 —
    collided with a seeded one and failed on `drugs_pkey`.

    The publish stage now resyncs as it goes; this repairs databases built
    before it did. Idempotent, and correct on an empty table: the
    three-argument `setval` sets `is_called` false so the next value is 1.
    """
    for table, column in (("drugs", "drug_id"), ("indications", "indication_id")):
        op.execute(
            f"SELECT setval("
            f"  pg_get_serial_sequence('{table}', '{column}'),"
            f"  COALESCE((SELECT MAX({column}) FROM {table}), 1),"
            f"  COALESCE((SELECT MAX({column}) FROM {table}), 0) > 0"
            f")"
        )


def downgrade() -> None:
    """Deliberately empty.

    The forward direction repairs a sequence that was behind its table.
    There is no meaningful reverse — putting it back would restore a state
    in which the next insert fails — and a downgrade that re-breaks the
    database is worse than one that does nothing.
    """
