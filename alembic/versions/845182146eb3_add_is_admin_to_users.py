"""add_is_admin_to_users

Revision ID: 845182146eb3
Revises: b2da5e3dfc5d
Create Date: 2025-08-20 13:12:52.278458

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '845182146eb3'
down_revision = 'b2da5e3dfc5d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_admin', sa.Boolean(),
                  nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('users', 'is_admin')
