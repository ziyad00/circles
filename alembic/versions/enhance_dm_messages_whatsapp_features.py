"""enhance dm messages with whatsapp features

Revision ID: enhance_dm_messages_whatsapp_features
Revises: 8b9d5d3a4af1
Create Date: 2025-01-18 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'enhance_dm_messages_whatsapp_features'
down_revision = '8b9d5d3a4af1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to dm_messages table
    op.add_column('dm_messages', sa.Column('delivery_status', sa.String(), nullable=False, server_default='sent'))
    op.add_column('dm_messages', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('dm_messages', sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('dm_messages', sa.Column('failure_reason', sa.String(), nullable=True))

    # Voice message support
    op.add_column('dm_messages', sa.Column('voice_urls', sa.JSON(), nullable=True))
    op.add_column('dm_messages', sa.Column('voice_duration', sa.Integer(), nullable=True))  # in seconds

    # File sharing
    op.add_column('dm_messages', sa.Column('file_urls', sa.JSON(), nullable=True))
    op.add_column('dm_messages', sa.Column('file_names', sa.JSON(), nullable=True))
    op.add_column('dm_messages', sa.Column('file_sizes', sa.JSON(), nullable=True))

    # Location sharing
    op.add_column('dm_messages', sa.Column('location_latitude', sa.Float(), nullable=True))
    op.add_column('dm_messages', sa.Column('location_longitude', sa.Float(), nullable=True))
    op.add_column('dm_messages', sa.Column('location_name', sa.String(), nullable=True))
    op.add_column('dm_messages', sa.Column('location_address', sa.String(), nullable=True))

    # Disappearing messages
    op.add_column('dm_messages', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('dm_messages', sa.Column('auto_delete_duration', sa.Integer(), nullable=True))  # in seconds

    # Forwarding
    op.add_column('dm_messages', sa.Column('forwarded_from_message_id', sa.Integer(), nullable=True))
    op.add_column('dm_messages', sa.Column('forwarded_from_user_id', sa.Integer(), nullable=True))
    op.add_column('dm_messages', sa.Column('is_forwarded', sa.Boolean(), nullable=False, server_default='false'))

    # Message type for better handling
    op.add_column('dm_messages', sa.Column('message_type', sa.String(), nullable=False, server_default='text'))

    # Deleted message placeholder
    op.add_column('dm_messages', sa.Column('deleted_by_user_id', sa.Integer(), nullable=True))

    # Add foreign key constraints
    op.create_foreign_key('fk_dm_messages_forwarded_from_message', 'dm_messages', 'dm_messages', ['forwarded_from_message_id'], ['id'])
    op.create_foreign_key('fk_dm_messages_forwarded_from_user', 'dm_messages', 'users', ['forwarded_from_user_id'], ['id'])
    op.create_foreign_key('fk_dm_messages_deleted_by_user', 'dm_messages', 'users', ['deleted_by_user_id'], ['id'])


def downgrade() -> None:
    # Remove foreign keys first
    op.drop_constraint('fk_dm_messages_deleted_by_user', 'dm_messages', type_='foreignkey')
    op.drop_constraint('fk_dm_messages_forwarded_from_user', 'dm_messages', type_='foreignkey')
    op.drop_constraint('fk_dm_messages_forwarded_from_message', 'dm_messages', type_='foreignkey')

    # Remove columns
    op.drop_column('dm_messages', 'deleted_by_user_id')
    op.drop_column('dm_messages', 'message_type')
    op.drop_column('dm_messages', 'is_forwarded')
    op.drop_column('dm_messages', 'forwarded_from_user_id')
    op.drop_column('dm_messages', 'forwarded_from_message_id')
    op.drop_column('dm_messages', 'auto_delete_duration')
    op.drop_column('dm_messages', 'expires_at')
    op.drop_column('dm_messages', 'location_address')
    op.drop_column('dm_messages', 'location_name')
    op.drop_column('dm_messages', 'location_longitude')
    op.drop_column('dm_messages', 'location_latitude')
    op.drop_column('dm_messages', 'file_sizes')
    op.drop_column('dm_messages', 'file_names')
    op.drop_column('dm_messages', 'file_urls')
    op.drop_column('dm_messages', 'voice_duration')
    op.drop_column('dm_messages', 'voice_urls')
    op.drop_column('dm_messages', 'failure_reason')
    op.drop_column('dm_messages', 'failed_at')
    op.drop_column('dm_messages', 'delivered_at')
    op.drop_column('dm_messages', 'delivery_status')