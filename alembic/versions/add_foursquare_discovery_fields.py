"""Add Foursquare discovery fields

Revision ID: add_foursquare_discovery_fields
Revises: add_coordinate_indexes
Create Date: 2024-08-24 05:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_foursquare_discovery_fields'
down_revision = 'add_coordinate_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Foursquare-specific fields
    op.add_column('places', sa.Column('fsq_id', sa.String(), nullable=True))
    op.add_column('places', sa.Column('seed_source', sa.String(), nullable=True, server_default='osm'))
    
    # Create unique index on fsq_id
    op.create_index('ix_places_fsq_id', 'places', ['fsq_id'], unique=True)
    
    # Create index on seed_source for filtering
    op.create_index('ix_places_seed_source', 'places', ['seed_source'])
    
    # Add constraint to ensure seed_source is valid
    op.execute("ALTER TABLE places ADD CONSTRAINT chk_seed_source CHECK (seed_source IN ('osm', 'fsq'))")


def downgrade() -> None:
    # Drop constraints and indexes
    op.execute("ALTER TABLE places DROP CONSTRAINT IF EXISTS chk_seed_source")
    op.drop_index('ix_places_seed_source', table_name='places')
    op.drop_index('ix_places_fsq_id', table_name='places')
    
    # Drop columns
    op.drop_column('places', 'seed_source')
    op.drop_column('places', 'fsq_id')
