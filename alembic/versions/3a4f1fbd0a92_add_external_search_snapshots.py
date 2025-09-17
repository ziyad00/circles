"""add external search snapshots table

Revision ID: 3a4f1fbd0a92
Revises: 499278ad9251
Create Date: 2025-09-17 13:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3a4f1fbd0a92'
down_revision = '499278ad9251'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'external_search_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('search_key', sa.String(length=255), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('radius_m', sa.Integer(), nullable=False),
        sa.Column('query', sa.String(), nullable=True),
        sa.Column('types', sa.String(), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=False, server_default='osm_overpass'),
        sa.Column('result_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('results', sa.JSON(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'ix_external_search_snapshots_search_key',
        'external_search_snapshots',
        ['search_key']
    )
    op.create_index(
        'ix_external_search_snapshots_fetched_at',
        'external_search_snapshots',
        ['fetched_at']
    )


def downgrade() -> None:
    op.drop_index('ix_external_search_snapshots_fetched_at', table_name='external_search_snapshots')
    op.drop_index('ix_external_search_snapshots_search_key', table_name='external_search_snapshots')
    op.drop_table('external_search_snapshots')
