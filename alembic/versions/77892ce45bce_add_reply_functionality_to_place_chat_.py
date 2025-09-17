"""Add reply functionality to place chat comments

Revision ID: 77892ce45bce
Revises: 7d69fd0df4e4
Create Date: 2025-09-17 20:51:57.001273

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '77892ce45bce'
down_revision = '7d69fd0df4e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add reply functionality to check_in_comments
    op.add_column('check_in_comments', sa.Column('reply_to_id', sa.Integer(), nullable=True))
    op.add_column('check_in_comments', sa.Column('reply_to_text', sa.Text(), nullable=True))

    # Add foreign key constraint and index
    op.create_foreign_key(
        'fk_check_in_comments_reply_to_id',
        'check_in_comments', 'check_in_comments',
        ['reply_to_id'], ['id']
    )
    op.create_index('ix_check_in_comments_reply_to_id', 'check_in_comments', ['reply_to_id'])


def downgrade() -> None:
    # Remove reply functionality from check_in_comments
    op.drop_index('ix_check_in_comments_reply_to_id', 'check_in_comments')
    op.drop_constraint('fk_check_in_comments_reply_to_id', 'check_in_comments', type_='foreignkey')
    op.drop_column('check_in_comments', 'reply_to_text')
    op.drop_column('check_in_comments', 'reply_to_id')
