"""Add PostGIS spatial index

Revision ID: add_postgis_spatial_index
Revises: e29f38437e12
Create Date: 2024-08-24 04:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_postgis_spatial_index'
down_revision = 'e29f38437e12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add PostGIS extension if not exists
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # Add geography column for spatial indexing
    op.execute("""
        ALTER TABLE places 
        ADD COLUMN IF NOT EXISTS location geography(POINT, 4326)
    """)

    # Update existing places with location data
    op.execute("""
        UPDATE places 
        SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography 
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)

    # Create spatial index
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_location 
        ON places USING GIST (location)
    """)

    # Create index on coordinates for non-spatial queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_coordinates 
        ON places (latitude, longitude)
    """)


def downgrade() -> None:
    # Drop spatial index
    op.execute("DROP INDEX IF EXISTS idx_places_location")

    # Drop coordinate index
    op.execute("DROP INDEX IF EXISTS idx_places_coordinates")

    # Drop geography column
    op.execute("ALTER TABLE places DROP COLUMN IF EXISTS location")
