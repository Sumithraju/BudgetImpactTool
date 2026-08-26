"""scenarios.is_archived for M1 soft delete

Revision ID: 12083c6e86b3
Revises: 94bcd9ad76be
Create Date: 2026-08-24 05:29:42.993141
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '12083c6e86b3'
down_revision: str | None = '94bcd9ad76be'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default is required, not decorative: the ORM's `default=False`
    # is applied by Python at insert time, so it does nothing for rows that
    # already exist. Adding a NOT NULL column without a database-side default
    # fails outright on a populated table.
    op.add_column(
        "scenarios",
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.false(),
        ),
    )
    # Drop the default once existing rows are backfilled: new rows get their
    # value from the ORM, and leaving it would let a future insert bypass the
    # application default silently.
    op.alter_column("scenarios", "is_archived", server_default=None)


def downgrade() -> None:
    op.drop_column("scenarios", "is_archived")
