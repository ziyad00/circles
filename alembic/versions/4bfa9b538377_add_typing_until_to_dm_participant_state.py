"""add typing_until to dm participant state

Revision ID: 4bfa9b538377
Revises: 56cd335cf832
Create Date: 2025-08-19 15:41:54.782991

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4bfa9b538377'
down_revision = '56cd335cf832'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('dm_participant_states', sa.Column('typing_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('dm_participant_states', 'typing_until')
