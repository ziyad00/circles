"""add description and price_tier to places

Revision ID: a3e573fe47f9
Revises: 81ef841e3c1e
Create Date: 2025-09-01 20:21:10.246197

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3e573fe47f9'
down_revision = '81ef841e3c1e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only add the new columns; do not drop PostGIS/Topology tables
    op.add_column('places', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('places', sa.Column('price_tier', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('places', 'price_tier')
    op.drop_column('places', 'description')
