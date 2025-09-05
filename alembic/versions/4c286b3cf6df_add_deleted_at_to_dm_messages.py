"""add_deleted_at_to_dm_messages

Revision ID: 4c286b3cf6df
Revises: 5133306800e6
Create Date: 2025-09-05 23:15:57.513994

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4c286b3cf6df'
down_revision = '5133306800e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add deleted_at column to dm_messages table
    op.add_column('dm_messages', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove deleted_at column from dm_messages table
    op.drop_column('dm_messages', 'deleted_at')
