"""comprehensive privacy controls

Revision ID: comprehensive_privacy_controls
Revises: enhance_dm_messages_whatsapp_features
Create Date: 2025-01-18 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'comprehensive_privacy_controls'
down_revision = 'enhance_dm_messages_whatsapp_features'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add comprehensive privacy controls to users table
    op.add_column('users', sa.Column('profile_visibility', sa.String(), nullable=False, server_default='public'))
    op.add_column('users', sa.Column('follower_list_visibility', sa.String(), nullable=False, server_default='public'))
    op.add_column('users', sa.Column('following_list_visibility', sa.String(), nullable=False, server_default='public'))
    op.add_column('users', sa.Column('stats_visibility', sa.String(), nullable=False, server_default='public'))
    op.add_column('users', sa.Column('media_default_visibility', sa.String(), nullable=False, server_default='public'))
    op.add_column('users', sa.Column('search_visibility', sa.String(), nullable=False, server_default='public'))

    # Update collections to use standardized visibility instead of is_public boolean
    # Add visibility column first
    op.add_column('user_collections', sa.Column('visibility', sa.String(), nullable=True))

    # Migrate existing is_public values to visibility
    # True -> 'public', False -> 'private'
    op.execute("""
        UPDATE user_collections
        SET visibility = CASE
            WHEN is_public = true THEN 'public'
            WHEN is_public = false THEN 'private'
            ELSE 'public'
        END
    """)

    # Make visibility non-nullable with default
    op.alter_column('user_collections', 'visibility', nullable=False, server_default='public')


def downgrade() -> None:
    # Remove new privacy columns from users
    op.drop_column('users', 'search_visibility')
    op.drop_column('users', 'media_default_visibility')
    op.drop_column('users', 'stats_visibility')
    op.drop_column('users', 'following_list_visibility')
    op.drop_column('users', 'follower_list_visibility')
    op.drop_column('users', 'profile_visibility')

    # Revert collections visibility changes
    op.drop_column('user_collections', 'visibility')