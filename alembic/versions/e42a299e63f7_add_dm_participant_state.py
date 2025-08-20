"""add dm participant state

Revision ID: e42a299e63f7
Revises: 4548bf12f4b2
Create Date: 2025-08-19 15:32:51.466854

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e42a299e63f7'
down_revision = '4548bf12f4b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'dm_participant_states',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('thread_id', sa.Integer(), sa.ForeignKey('dm_threads.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('muted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_dm_participant_states_thread_id', 'dm_participant_states', ['thread_id'])
    op.create_index('ix_dm_participant_states_user_id', 'dm_participant_states', ['user_id'])
    op.create_unique_constraint('uq_dm_participant_states_thread_user', 'dm_participant_states', ['thread_id', 'user_id'])


def downgrade() -> None:
    op.drop_constraint('uq_dm_participant_states_thread_user', 'dm_participant_states', type_='unique')
    op.drop_index('ix_dm_participant_states_user_id', table_name='dm_participant_states')
    op.drop_index('ix_dm_participant_states_thread_id', table_name='dm_participant_states')
    op.drop_table('dm_participant_states')
