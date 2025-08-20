"""profiles_avatar_support_and_interests

Revision ID: ffc0b57fb186
Revises: a821e0a728a5
Create Date: 2025-08-20 12:19:33.300995

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ffc0b57fb186'
down_revision = 'a821e0a728a5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('name', sa.String(), nullable=True))
    op.add_column('users', sa.Column('bio', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('avatar_url', sa.String(), nullable=True))

    op.create_table(
        'support_tickets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_support_tickets_id'), 'support_tickets', ['id'], unique=False)
    op.create_index(op.f('ix_support_tickets_user_id'), 'support_tickets', ['user_id'], unique=False)

    op.create_table(
        'user_interests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_interests_id'), 'user_interests', ['id'], unique=False)
    op.create_index(op.f('ix_user_interests_user_id'), 'user_interests', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_interests_name'), 'user_interests', ['name'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_interests_name'), table_name='user_interests')
    op.drop_index(op.f('ix_user_interests_user_id'), table_name='user_interests')
    op.drop_index(op.f('ix_user_interests_id'), table_name='user_interests')
    op.drop_table('user_interests')

    op.drop_index(op.f('ix_support_tickets_user_id'), table_name='support_tickets')
    op.drop_index(op.f('ix_support_tickets_id'), table_name='support_tickets')
    op.drop_table('support_tickets')

    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'bio')
    op.drop_column('users', 'name')
