"""add place chat messages table

Revision ID: place_chat_messages
Revises: 77892ce45bce
Create Date: 2025-09-26 05:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'place_chat_messages'
down_revision = '77892ce45bce'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'place_chat_messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('place_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['place_id'], ['places.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_place_chat_messages_place_id', 'place_chat_messages', ['place_id'])
    op.create_index('ix_place_chat_messages_user_id', 'place_chat_messages', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_place_chat_messages_user_id', table_name='place_chat_messages')
    op.drop_index('ix_place_chat_messages_place_id', table_name='place_chat_messages')
    op.drop_table('place_chat_messages')
