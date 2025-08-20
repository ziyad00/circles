"""add dm tables

Revision ID: 4548bf12f4b2
Revises: 6f86a9fd8f77
Create Date: 2025-08-19 15:28:57.141976

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4548bf12f4b2'
down_revision = '6f86a9fd8f77'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'dm_threads',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_a_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('user_b_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('initiator_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_dm_threads_user_a_id', 'dm_threads', ['user_a_id'])
    op.create_index('ix_dm_threads_user_b_id', 'dm_threads', ['user_b_id'])
    op.create_index('ix_dm_threads_initiator_id', 'dm_threads', ['initiator_id'])

    op.create_table(
        'dm_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('thread_id', sa.Integer(), sa.ForeignKey('dm_threads.id'), nullable=False),
        sa.Column('sender_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_dm_messages_thread_id', 'dm_messages', ['thread_id'])
    op.create_index('ix_dm_messages_sender_id', 'dm_messages', ['sender_id'])


def downgrade() -> None:
    op.drop_index('ix_dm_messages_sender_id', table_name='dm_messages')
    op.drop_index('ix_dm_messages_thread_id', table_name='dm_messages')
    op.drop_table('dm_messages')
    op.drop_index('ix_dm_threads_initiator_id', table_name='dm_threads')
    op.drop_index('ix_dm_threads_user_b_id', table_name='dm_threads')
    op.drop_index('ix_dm_threads_user_a_id', table_name='dm_threads')
    op.drop_table('dm_threads')
