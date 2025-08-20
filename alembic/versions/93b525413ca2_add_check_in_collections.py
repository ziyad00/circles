"""add_check_in_collections

Revision ID: 93b525413ca2
Revises: 946130765206
Create Date: 2025-08-20 11:33:07.431250

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '93b525413ca2'
down_revision = '946130765206'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'check_in_collections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_check_in_collections_id'), 'check_in_collections', ['id'], unique=False)
    op.create_index(op.f('ix_check_in_collections_user_id'), 'check_in_collections', ['user_id'], unique=False)

    op.create_table(
        'check_in_collection_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('collection_id', sa.Integer(), nullable=False),
        sa.Column('check_in_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['collection_id'], ['check_in_collections.id'], ),
        sa.ForeignKeyConstraint(['check_in_id'], ['check_ins.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_check_in_collection_items_id'), 'check_in_collection_items', ['id'], unique=False)
    op.create_index(op.f('ix_check_in_collection_items_collection_id'), 'check_in_collection_items', ['collection_id'], unique=False)
    op.create_index(op.f('ix_check_in_collection_items_check_in_id'), 'check_in_collection_items', ['check_in_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_check_in_collection_items_check_in_id'), table_name='check_in_collection_items')
    op.drop_index(op.f('ix_check_in_collection_items_collection_id'), table_name='check_in_collection_items')
    op.drop_index(op.f('ix_check_in_collection_items_id'), table_name='check_in_collection_items')
    op.drop_table('check_in_collection_items')

    op.drop_index(op.f('ix_check_in_collections_user_id'), table_name='check_in_collections')
    op.drop_index(op.f('ix_check_in_collections_id'), table_name='check_in_collections')
    op.drop_table('check_in_collections')
