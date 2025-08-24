"""Add coordinate indexes for better geospatial performance

Revision ID: add_coordinate_indexes
Revises: e29f38437e12
Create Date: 2024-08-24 04:50:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_coordinate_indexes'
down_revision = 'e29f38437e12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create index on coordinates for better geospatial queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_coordinates 
        ON places (latitude, longitude)
    """)

    # Create index on external_id for faster lookups
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_external_id 
        ON places (external_id, data_source)
    """)

    # Create index on categories for faster filtering
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_categories 
        ON places USING gin(to_tsvector('english', categories))
    """)

    # Create index on name for faster text search
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_name 
        ON places USING gin(to_tsvector('english', name))
    """)


def downgrade() -> None:
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_places_coordinates")
    op.execute("DROP INDEX IF EXISTS idx_places_external_id")
    op.execute("DROP INDEX IF EXISTS idx_places_categories")
    op.execute("DROP INDEX IF EXISTS idx_places_name")
