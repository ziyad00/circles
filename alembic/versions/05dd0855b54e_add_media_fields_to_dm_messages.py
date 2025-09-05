"""add_media_fields_to_dm_messages

Revision ID: 05dd0855b54e
Revises: 93c1b6e93c5a
Create Date: 2025-09-05 23:48:29.660448

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '05dd0855b54e'
down_revision = '93c1b6e93c5a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add media fields to dm_messages table
    op.add_column('dm_messages', sa.Column(
        'photo_urls', sa.JSON(), nullable=True, default=list))
    op.add_column('dm_messages', sa.Column(
        'video_urls', sa.JSON(), nullable=True, default=list))


def downgrade() -> None:
    # Remove media fields from dm_messages table
    op.drop_column('dm_messages', 'video_urls')
    op.drop_column('dm_messages', 'photo_urls')
