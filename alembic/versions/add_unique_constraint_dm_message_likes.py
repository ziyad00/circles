"""add unique constraint to dm_message_likes

Revision ID: add_unique_constraint_dm_message_likes
Revises: 01b61feb1db0
Create Date: 2025-08-24 06:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_dm_likes_unique'
down_revision = '01b61feb1db0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unique constraint to prevent duplicate likes
    op.create_unique_constraint('uq_dm_message_like_user', 'dm_message_likes', [
                                'message_id', 'user_id'])


def downgrade() -> None:
    # Remove unique constraint
    op.drop_constraint('uq_dm_message_like_user',
                       'dm_message_likes', type_='unique')
