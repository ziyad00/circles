"""add country to places

Revision ID: 5133306800e6
Revises: a3e573fe47f9
Create Date: 2025-09-01 21:06:14.528533

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5133306800e6'
down_revision = 'a3e573fe47f9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('places', sa.Column('country', sa.String(), nullable=True))
    op.create_index(op.f('ix_places_country'), 'places', ['country'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_places_country'), table_name='places')
    op.drop_column('places', 'country')
