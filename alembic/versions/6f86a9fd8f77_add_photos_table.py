"""add photos table

Revision ID: 6f86a9fd8f77
Revises: c2c291470184
Create Date: 2025-08-19 15:12:09.168166

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6f86a9fd8f77'
down_revision = 'c2c291470184'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'photos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey(
            'users.id'), nullable=False),
        sa.Column('place_id', sa.Integer(), sa.ForeignKey(
            'places.id'), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index('ix_photos_user_id', 'photos', ['user_id'])
    op.create_index('ix_photos_place_id', 'photos', ['place_id'])


def downgrade() -> None:
    op.drop_index('ix_photos_place_id', table_name='photos')
    op.drop_index('ix_photos_user_id', table_name='photos')
    op.drop_table('photos')
