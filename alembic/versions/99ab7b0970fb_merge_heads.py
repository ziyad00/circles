"""merge_heads

Revision ID: 99ab7b0970fb
Revises: 77892ce45bce, c9fd549d5f23, comprehensive_privacy_controls
Create Date: 2025-09-19 22:06:02.522063

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '99ab7b0970fb'
down_revision = ('77892ce45bce', 'c9fd549d5f23', 'comprehensive_privacy_controls')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
