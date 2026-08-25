"""comparator registry for M12

Creates `comparator_assets` and `comparator_approvals` (ARCHITECTURE.md 8.4).
`comparator_assets.drug_id` is nullable on purpose: null is the flag that a
molecule is known about but has no price or regimen, and so cannot enter a
calculation (M12 section 5.4).

Revision ID: d07438e081b4
Revises: 12083c6e86b3
Create Date: 2026-08-25 14:52:46.292088
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd07438e081b4'
down_revision: str | None = '12083c6e86b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('comparator_assets',
    sa.Column('asset_id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Text(), nullable=False),
    sa.Column('asset_name', sa.Text(), nullable=False),
    sa.Column('indication_id', sa.Integer(), nullable=False),
    sa.Column('target_symbol', sa.Text(), nullable=False),
    sa.Column('target_id', sa.Text(), nullable=True),
    sa.Column('mechanism_of_action', sa.Text(), nullable=True),
    sa.Column('action_type', sa.Text(), nullable=True),
    sa.Column('pathway_ids', sa.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('drug_type', sa.Text(), nullable=True),
    sa.Column('max_clinical_stage', sa.Text(), nullable=False),
    sa.Column('competitor_class', sa.Text(), nullable=False),
    sa.Column('relevance', sa.Numeric(precision=6, scale=4), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('brand_name', sa.Text(), nullable=True),
    sa.Column('manufacturer', sa.Text(), nullable=True),
    sa.Column('route', sa.Text(), nullable=True),
    sa.Column('line_of_therapy', sa.Text(), nullable=True),
    sa.Column('sponsor', sa.Text(), nullable=True),
    sa.Column('primary_completion', sa.Date(), nullable=True),
    sa.Column('expected_entry_year', sa.SmallInteger(), nullable=True),
    sa.Column('assumed_terminal_pct', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('is_new_asset', sa.Boolean(), nullable=False),
    sa.Column('drug_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('confidence_tier', sa.CHAR(length=1), nullable=False),
    sa.CheckConstraint('assumed_terminal_pct IS NULL OR (assumed_terminal_pct > 0 AND assumed_terminal_pct < 1)', name='ck_comparator_assets_terminal_share'),
    sa.CheckConstraint('relevance >= 0 AND relevance <= 1', name='ck_comparator_assets_relevance'),
    sa.ForeignKeyConstraint(['drug_id'], ['drugs.drug_id'], ),
    sa.ForeignKeyConstraint(['indication_id'], ['indications.indication_id'], ),
    sa.PrimaryKeyConstraint('asset_id'),
    sa.UniqueConstraint('source_id', 'indication_id', name='uq_comparator_assets_natural')
    )
    op.create_table('comparator_approvals',
    sa.Column('approval_id', sa.Integer(), nullable=False),
    sa.Column('asset_id', sa.Integer(), nullable=False),
    sa.Column('country_code', sa.CHAR(length=3), nullable=False),
    sa.Column('approval_year', sa.SmallInteger(), nullable=True),
    sa.Column('is_reimbursed', sa.Boolean(), nullable=True),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('confidence_tier', sa.CHAR(length=1), nullable=False),
    sa.ForeignKeyConstraint(['asset_id'], ['comparator_assets.asset_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['country_code'], ['countries.country_code'], ),
    sa.PrimaryKeyConstraint('approval_id'),
    sa.UniqueConstraint('asset_id', 'country_code', name='uq_comparator_approvals_natural')
    )
    # The registry is always read filtered by indication, usually by class as
    # well — that is the shape of every listing the interface asks for.
    op.create_index(
        'ix_comparator_assets_indication_class',
        'comparator_assets', ['indication_id', 'competitor_class'],
    )


def downgrade() -> None:
    op.drop_table('comparator_approvals')
    op.drop_table('comparator_assets')
