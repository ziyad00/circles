"""Backfill saved places into user collections

Revision ID: c9fd549d5f23
Revises: 8b9d5d3a4af1
Create Date: 2025-09-17 23:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9fd549d5f23"
down_revision = "8b9d5d3a4af1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Create missing collections for saved places (trim names, default Favorites)
    conn.execute(sa.text(
        """
        INSERT INTO user_collections (user_id, name, description, is_public, created_at)
        SELECT
            sp.user_id,
            COALESCE(NULLIF(TRIM(sp.list_name), ''), 'Favorites') AS name,
            NULL,
            true,
            COALESCE(MIN(sp.created_at), CURRENT_TIMESTAMP)
        FROM saved_places sp
        LEFT JOIN user_collections uc
            ON uc.user_id = sp.user_id
           AND uc.name = COALESCE(NULLIF(TRIM(sp.list_name), ''), 'Favorites')
        WHERE uc.id IS NULL
        GROUP BY sp.user_id, COALESCE(NULLIF(TRIM(sp.list_name), ''), 'Favorites')
        """
    ))

    # Insert missing collection/place links for saved places
    conn.execute(sa.text(
        """
        INSERT INTO user_collection_places (collection_id, place_id, added_at)
        SELECT
            uc.id,
            sp.place_id,
            COALESCE(sp.created_at, CURRENT_TIMESTAMP)
        FROM saved_places sp
        JOIN user_collections uc
          ON uc.user_id = sp.user_id
         AND uc.name = COALESCE(NULLIF(TRIM(sp.list_name), ''), 'Favorites')
        LEFT JOIN user_collection_places ucp
          ON ucp.collection_id = uc.id
         AND ucp.place_id = sp.place_id
        WHERE ucp.id IS NULL
        """
    ))


def downgrade() -> None:
    conn = op.get_bind()

    # Remove collection/place links that mirror saved places
    conn.execute(sa.text(
        """
        DELETE FROM user_collection_places
        WHERE id IN (
            SELECT ucp.id
            FROM user_collection_places ucp
            JOIN user_collections uc
              ON uc.id = ucp.collection_id
            JOIN saved_places sp
              ON sp.user_id = uc.user_id
             AND sp.place_id = ucp.place_id
             AND uc.name = COALESCE(NULLIF(TRIM(sp.list_name), ''), 'Favorites')
        )
        """
    ))

    # Remove empty collections created by the backfill
    conn.execute(sa.text(
        """
        DELETE FROM user_collections uc
        WHERE NOT EXISTS (
            SELECT 1 FROM user_collection_places ucp
            WHERE ucp.collection_id = uc.id
        )
        """
    ))
