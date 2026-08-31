"""add EviTrack evidence records

Revision ID: f3593de96a10
Revises: 5622a3993aaf
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3593de96a10"
down_revision: str | None = "5622a3993aaf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_records",
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", sa.Text(), nullable=True),
        sa.Column("publication_date", sa.Text(), nullable=True),
        sa.Column("doi", sa.Text(), nullable=True),
        sa.Column("evidence_type", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("evidence_id"),
    )


def downgrade() -> None:
    op.drop_table("evidence_records")
