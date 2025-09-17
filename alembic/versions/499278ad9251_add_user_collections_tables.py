"""add_user_collections_tables

Revision ID: 499278ad9251
Revises: fdeec55cbdb7
Create Date: 2025-09-13 01:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '499278ad9251'
down_revision = 'fdeec55cbdb7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_collections table
    op.create_table(
        'user_collections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create index on user_id for better query performance
    op.create_index(op.f('ix_user_collections_user_id'),
                    'user_collections', ['user_id'], unique=False)

    # Create user_collection_places table
    op.create_table(
        'user_collection_places',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('collection_id', sa.Integer(), nullable=False),
        sa.Column('place_id', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['collection_id'], ['user_collections.id'], ),
        sa.ForeignKeyConstraint(['place_id'], ['places.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for better query performance
    op.create_index(op.f('ix_user_collection_places_collection_id'),
                    'user_collection_places', ['collection_id'], unique=False)
    op.create_index(op.f('ix_user_collection_places_place_id'),
                    'user_collection_places', ['place_id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order (due to foreign key constraints)
    op.drop_index(op.f('ix_user_collection_places_place_id'),
                  table_name='user_collection_places')
    op.drop_index(op.f('ix_user_collection_places_collection_id'),
                  table_name='user_collection_places')
    op.drop_table('user_collection_places')

    op.drop_index(op.f('ix_user_collections_user_id'),
                  table_name='user_collections')
    op.drop_table('user_collections')
    # Legacy cleanup: drop old check-in collections if present
    try:
        op.drop_table('check_in_collection_items')
    except Exception:
        pass
    try:
        op.drop_table('check_in_collections')
    except Exception:
        pass
