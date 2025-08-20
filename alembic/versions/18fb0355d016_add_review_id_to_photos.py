"""add review_id to photos

Revision ID: 18fb0355d016
Revises: fd86867e4a31
Create Date: 2025-08-20 10:34:35.138009

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '18fb0355d016'
down_revision = 'fd86867e4a31'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('photos', sa.Column(
        'review_id', sa.Integer(), nullable=True))
    op.create_index('ix_photos_review_id', 'photos', ['review_id'])
    op.create_foreign_key('fk_photos_review_id_reviews',
                          'photos', 'reviews', ['review_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_photos_review_id_reviews',
                       'photos', type_='foreignkey')
    op.drop_index('ix_photos_review_id', table_name='photos')
    op.drop_column('photos', 'review_id')
