"""user_privacy_defaults_and_collection_visibility

Revision ID: a821e0a728a5
Revises: 93b525413ca2
Create Date: 2025-08-20 11:57:18.000695

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a821e0a728a5'
down_revision = '93b525413ca2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # user privacy/defaults
    op.add_column('users', sa.Column('dm_privacy', sa.String(), nullable=False, server_default='everyone'))
    op.add_column('users', sa.Column('checkins_default_visibility', sa.String(), nullable=False, server_default='public'))
    op.add_column('users', sa.Column('collections_default_visibility', sa.String(), nullable=False, server_default='public'))
    # collection visibility
    op.add_column('check_in_collections', sa.Column('visibility', sa.String(), nullable=False, server_default='public'))


def downgrade() -> None:
    op.drop_column('check_in_collections', 'visibility')
    op.drop_column('users', 'collections_default_visibility')
    op.drop_column('users', 'checkins_default_visibility')
    op.drop_column('users', 'dm_privacy')
