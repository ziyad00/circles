"""reviews and my_checkins

Revision ID: 31d536d92ca5
Revises: 90bfafc9d11a
Create Date: 2025-08-19 12:06:06.926067

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '31d536d92ca5'
down_revision = '90bfafc9d11a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unique constraints to prevent duplicates
    op.create_unique_constraint(
        'uq_reviews_user_place', 'reviews', ['user_id', 'place_id']
    )
    op.create_unique_constraint(
        'uq_saved_places_user_place', 'saved_places', ['user_id', 'place_id']
    )
    # Add check constraints for data integrity
    op.create_check_constraint(
        'ck_reviews_rating_range', 'reviews', 'rating >= 0 AND rating <= 5'
    )
    op.create_check_constraint(
        'ck_checkins_visibility', 'check_ins', "visibility IN ('public','friends','private')"
    )


def downgrade() -> None:
    op.drop_constraint('uq_saved_places_user_place', 'saved_places', type_='unique')
    op.drop_constraint('uq_reviews_user_place', 'reviews', type_='unique')
    op.drop_constraint('ck_checkins_visibility', 'check_ins', type_='check')
    op.drop_constraint('ck_reviews_rating_range', 'reviews', type_='check')
