"""add photo_url to check_ins

Revision ID: bc086377c0d1
Revises: 18fb0355d016
Create Date: 2025-08-20 10:58:53.777049

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bc086377c0d1'
down_revision = '18fb0355d016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('check_ins', sa.Column('photo_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('check_ins', 'photo_url')
