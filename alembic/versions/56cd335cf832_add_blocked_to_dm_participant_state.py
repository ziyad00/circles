"""add blocked to dm participant state

Revision ID: 56cd335cf832
Revises: e42a299e63f7
Create Date: 2025-08-19 15:38:02.681049

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '56cd335cf832'
down_revision = 'e42a299e63f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('dm_participant_states', sa.Column('blocked', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('dm_participant_states', 'blocked')
