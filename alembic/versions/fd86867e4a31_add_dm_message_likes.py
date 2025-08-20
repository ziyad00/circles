"""add dm message likes

Revision ID: fd86867e4a31
Revises: 4bfa9b538377
Create Date: 2025-08-19 15:45:40.463058

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fd86867e4a31'
down_revision = '4bfa9b538377'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'dm_message_likes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('message_id', sa.Integer(), sa.ForeignKey('dm_messages.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_dm_message_likes_message_id', 'dm_message_likes', ['message_id'])
    op.create_index('ix_dm_message_likes_user_id', 'dm_message_likes', ['user_id'])
    op.create_unique_constraint('uq_dm_message_likes_message_user', 'dm_message_likes', ['message_id', 'user_id'])


def downgrade() -> None:
    op.drop_constraint('uq_dm_message_likes_message_user', 'dm_message_likes', type_='unique')
    op.drop_index('ix_dm_message_likes_user_id', table_name='dm_message_likes')
    op.drop_index('ix_dm_message_likes_message_id', table_name='dm_message_likes')
    op.drop_table('dm_message_likes')
