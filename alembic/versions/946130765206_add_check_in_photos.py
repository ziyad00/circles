"""add_check_in_photos

Revision ID: 946130765206
Revises: 684d326594c5
Create Date: 2025-08-20 11:28:17.681793

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '946130765206'
down_revision = '684d326594c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'check_in_photos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('check_in_id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['check_in_id'], ['check_ins.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_check_in_photos_id'), 'check_in_photos', ['id'], unique=False)
    op.create_index(op.f('ix_check_in_photos_check_in_id'), 'check_in_photos', ['check_in_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_check_in_photos_check_in_id'), table_name='check_in_photos')
    op.drop_index(op.f('ix_check_in_photos_id'), table_name='check_in_photos')
    op.drop_table('check_in_photos')
