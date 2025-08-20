"""add follows table

Revision ID: 684d326594c5
Revises: bc086377c0d1
Create Date: 2025-08-20 11:08:14.201907

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '684d326594c5'
down_revision = 'bc086377c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'follows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('follower_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('followee_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_follows_follower_id', 'follows', ['follower_id'])
    op.create_index('ix_follows_followee_id', 'follows', ['followee_id'])
    op.create_unique_constraint('uq_follows_pair', 'follows', ['follower_id', 'followee_id'])


def downgrade() -> None:
    op.drop_constraint('uq_follows_pair', 'follows', type_='unique')
    op.drop_index('ix_follows_followee_id', table_name='follows')
    op.drop_index('ix_follows_follower_id', table_name='follows')
    op.drop_table('follows')
