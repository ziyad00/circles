"""add_reply_fields_to_dm_messages

Revision ID: 93c1b6e93c5a
Revises: 4c286b3cf6df
Create Date: 2025-09-05 23:40:55.245491

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '93c1b6e93c5a'
down_revision = '4c286b3cf6df'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add reply fields to dm_messages table
    op.add_column('dm_messages', sa.Column(
        'reply_to_id', sa.Integer(), nullable=True))
    op.add_column('dm_messages', sa.Column(
        'reply_to_text', sa.Text(), nullable=True))

    # Create foreign key constraint
    op.create_foreign_key(
        'fk_dm_messages_reply_to_id',
        'dm_messages', 'dm_messages',
        ['reply_to_id'], ['id']
    )

    # Create index for performance
    op.create_index('ix_dm_messages_reply_to_id',
                    'dm_messages', ['reply_to_id'])


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_dm_messages_reply_to_id')

    # Remove foreign key constraint
    op.drop_constraint('fk_dm_messages_reply_to_id',
                       'dm_messages', type_='foreignkey')

    # Remove columns
    op.drop_column('dm_messages', 'reply_to_text')
    op.drop_column('dm_messages', 'reply_to_id')
