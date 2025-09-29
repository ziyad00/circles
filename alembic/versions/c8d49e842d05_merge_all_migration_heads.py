"""Merge all migration heads

Revision ID: c8d49e842d05
Revises: add_photos_001, add_postal_code, comprehensive_privacy_controls, place_chat_messages
Create Date: 2025-09-27 12:11:54.523203

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8d49e842d05'
down_revision = ('add_photos_001', 'add_postal_code', 'comprehensive_privacy_controls', 'place_chat_messages')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
