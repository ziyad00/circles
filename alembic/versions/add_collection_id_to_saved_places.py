"""add collection_id to saved_places

Revision ID: abc123456789
Revises: 38ac4358ad74
Create Date: 2025-09-30 11:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'abc123456789'
down_revision = '38ac4358ad74'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add collection_id column to saved_places table if it doesn't exist
    conn = op.get_bind()

    # Check if column exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name='saved_places'
            AND column_name='collection_id'
        );
    """))
    column_exists = result.scalar()

    if not column_exists:
        # Add the column
        op.add_column('saved_places',
            sa.Column('collection_id', sa.Integer(), nullable=True))

        # Add foreign key constraint
        op.create_foreign_key(
            'fk_saved_places_collection_id',
            'saved_places', 'user_collections',
            ['collection_id'], ['id']
        )

        # Create index for better query performance
        op.create_index(
            'ix_saved_places_collection_id',
            'saved_places',
            ['collection_id']
        )
    else:
        print("collection_id column already exists in saved_places table")


def downgrade() -> None:
    # Remove the column and constraints
    op.drop_index('ix_saved_places_collection_id', table_name='saved_places')
    op.drop_constraint('fk_saved_places_collection_id', 'saved_places', type_='foreignkey')
    op.drop_column('saved_places', 'collection_id')