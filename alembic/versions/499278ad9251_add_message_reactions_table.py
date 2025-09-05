"""add_message_reactions_table

Revision ID: 499278ad9251
Revises: fdeec55cbdb7
Create Date: 2025-09-06 00:12:39.497402

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '499278ad9251'
down_revision = 'fdeec55cbdb7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create dm_message_reactions table
    op.create_table(
        'dm_message_reactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('emoji', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['message_id'], ['dm_messages.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'user_id', 'emoji', name='uq_dm_message_reaction_user_emoji')
    )

    # Create index for performance
    op.create_index('ix_dm_message_reactions_message_id', 'dm_message_reactions', ['message_id'])


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_dm_message_reactions_message_id', table_name='dm_message_reactions')

    # Drop table
    op.drop_table('dm_message_reactions')
