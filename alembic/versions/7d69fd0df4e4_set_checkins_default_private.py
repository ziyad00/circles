"""set check-ins default privacy to private

Revision ID: 7d69fd0df4e4
Revises: 3a4f1fbd0a92
Create Date: 2025-09-17 14:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7d69fd0df4e4'
down_revision = '3a4f1fbd0a92'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'users',
        'checkins_default_visibility',
        existing_type=sa.String(),
        server_default='private',
    )
    op.execute(
        """
        UPDATE users
        SET checkins_default_visibility = 'private'
        WHERE checkins_default_visibility IS NULL
           OR checkins_default_visibility = 'public'
        """
    )


def downgrade() -> None:
    op.alter_column(
        'users',
        'checkins_default_visibility',
        existing_type=sa.String(),
        server_default='public',
    )
