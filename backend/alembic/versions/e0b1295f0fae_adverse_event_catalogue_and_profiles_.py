"""adverse event catalogue and profiles for M13

Creates `adverse_events`, `adverse_event_costs` and `drug_adverse_events`
(ARCHITECTURE.md 8.4). `drug_adverse_events.confidence_tier` is NOT NULL with
no default on purpose: an adverse-event incidence is the value in this system
most likely to be repeated as fact, so it cannot be written without a stated
tier and source.

Revision ID: e0b1295f0fae
Revises: 6418e7ab2864
Create Date: 2026-08-25 15:09:42.573164
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e0b1295f0fae'
down_revision: str | None = '6418e7ab2864'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('adverse_events',
    sa.Column('ae_code', sa.Text(), nullable=False),
    sa.Column('ae_label', sa.Text(), nullable=False),
    sa.Column('is_serious', sa.Boolean(), nullable=False),
    sa.Column('meddra_pt', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('ae_code')
    )
    op.create_table('adverse_event_costs',
    sa.Column('ae_cost_id', sa.Integer(), nullable=False),
    sa.Column('ae_code', sa.Text(), nullable=False),
    sa.Column('country_code', sa.CHAR(length=3), nullable=False),
    sa.Column('unit_cost_local', sa.Numeric(), nullable=False),
    sa.Column('currency_code', sa.CHAR(length=3), nullable=False),
    sa.Column('cost_year', sa.SmallInteger(), nullable=True),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('confidence_tier', sa.CHAR(length=1), nullable=False),
    sa.CheckConstraint('unit_cost_local >= 0', name='ck_ae_costs_non_negative'),
    sa.ForeignKeyConstraint(['ae_code'], ['adverse_events.ae_code'], ),
    sa.ForeignKeyConstraint(['country_code'], ['countries.country_code'], ),
    sa.PrimaryKeyConstraint('ae_cost_id'),
    sa.UniqueConstraint('ae_code', 'country_code', name='uq_ae_costs_natural')
    )
    op.create_table('drug_adverse_events',
    sa.Column('dae_id', sa.Integer(), nullable=False),
    sa.Column('drug_id', sa.Integer(), nullable=False),
    sa.Column('ae_code', sa.Text(), nullable=False),
    sa.Column('incidence', sa.Numeric(precision=6, scale=5), nullable=False),
    sa.Column('exposure_weeks', sa.SmallInteger(), nullable=True),
    sa.Column('population', sa.Text(), nullable=True),
    sa.Column('evidence_type', sa.Text(), nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('vintage_year', sa.SmallInteger(), nullable=True),
    sa.Column('confidence_tier', sa.CHAR(length=1), nullable=False),
    sa.CheckConstraint('exposure_weeks IS NULL OR exposure_weeks > 0', name='ck_drug_adverse_events_exposure'),
    sa.CheckConstraint('incidence >= 0 AND incidence <= 1', name='ck_drug_adverse_events_incidence'),
    sa.ForeignKeyConstraint(['ae_code'], ['adverse_events.ae_code'], ),
    sa.ForeignKeyConstraint(['drug_id'], ['drugs.drug_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('dae_id'),
    sa.UniqueConstraint('drug_id', 'ae_code', name='uq_drug_adverse_events_natural')
    )
    op.drop_index(op.f('ix_comparator_assets_indication_class'), table_name='comparator_assets')


def downgrade() -> None:
    op.create_index(op.f('ix_comparator_assets_indication_class'), 'comparator_assets', ['indication_id', 'competitor_class'], unique=False)
    op.drop_table('drug_adverse_events')
    op.drop_table('adverse_event_costs')
    op.drop_table('adverse_events')
