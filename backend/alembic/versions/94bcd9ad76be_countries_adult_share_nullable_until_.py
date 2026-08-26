"""countries adult_share nullable until worldbank publishes

Revision ID: 94bcd9ad76be
Revises: bae9187702f7
Create Date: 2026-08-23 19:56:29.107823
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '94bcd9ad76be'
down_revision: str | None = 'bae9187702f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column('countries', 'adult_share',
               existing_type=sa.NUMERIC(precision=5, scale=4),
               nullable=True)
    op.alter_column('countries', 'adult_share_source',
               existing_type=sa.TEXT(),
               nullable=True)
    # Autogenerate detects the nullability change above but not this range
    # constraint's body, since it compares check constraints by name only.
    op.drop_constraint('ck_countries_adult_share_range', 'countries', type_='check')
    op.create_check_constraint(
        'ck_countries_adult_share_range',
        'countries',
        'adult_share IS NULL OR (adult_share > 0.5 AND adult_share < 0.95)',
    )


def downgrade() -> None:
    op.drop_constraint('ck_countries_adult_share_range', 'countries', type_='check')
    op.create_check_constraint(
        'ck_countries_adult_share_range',
        'countries',
        'adult_share > 0.5 AND adult_share < 0.95',
    )
    op.alter_column('countries', 'adult_share_source',
               existing_type=sa.TEXT(),
               nullable=False)
    op.alter_column('countries', 'adult_share',
               existing_type=sa.NUMERIC(precision=5, scale=4),
               nullable=False)
