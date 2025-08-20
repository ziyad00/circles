"""add_postgis_location_and_index_on_places

Revision ID: b2da5e3dfc5d
Revises: ffc0b57fb186
Create Date: 2025-08-20 13:08:28.886078

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2da5e3dfc5d'
down_revision = 'ffc0b57fb186'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Check if postgis is available on this server
    available = conn.execute(sa.text("SELECT COUNT(*) FROM pg_available_extensions WHERE name='postgis'"))
    if available.scalar() == 0:
        # Extension not installed on server; skip adding column/index
        return
    # Create extension if possible
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
    # Add geography column using raw SQL to ensure proper type
    conn.execute(sa.text("ALTER TABLE places ADD COLUMN IF NOT EXISTS location geography(Point,4326)"))
    conn.execute(sa.text("UPDATE places SET location = CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography END"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_places_location ON places USING GIST (location)"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_places_location"))
    conn.execute(sa.text("ALTER TABLE places DROP COLUMN IF EXISTS location"))
