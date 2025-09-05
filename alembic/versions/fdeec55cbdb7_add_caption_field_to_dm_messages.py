"""add_caption_field_to_dm_messages

Revision ID: fdeec55cbdb7
Revises: 05dd0855b54e
Create Date: 2025-09-06 00:01:48.921061

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fdeec55cbdb7'
down_revision = '05dd0855b54e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add caption field to dm_messages table
    op.add_column('dm_messages', sa.Column('caption', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove caption field from dm_messages table
    op.drop_column('dm_messages', 'caption')
