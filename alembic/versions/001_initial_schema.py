"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2025-08-25 01:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table first (base table for all relationships)
    op.create_table('users',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('email', sa.String(), nullable=True),
                    sa.Column('phone', sa.String(), nullable=True),
                    sa.Column('username', sa.String(), nullable=True),
                    sa.Column('is_verified', sa.Boolean(), nullable=True),
                    sa.Column('is_admin', sa.Boolean(), nullable=True),
                    sa.Column('name', sa.String(), nullable=True),
                    sa.Column('bio', sa.Text(), nullable=True),
                    sa.Column('avatar_url', sa.String(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.Column('updated_at', sa.DateTime(
                        timezone=True), nullable=True),
                    sa.Column('dm_privacy', sa.String(), nullable=False,
                              server_default='everyone'),
                    sa.Column('checkins_default_visibility', sa.String(),
                              nullable=False, server_default='public'),
                    sa.Column('collections_default_visibility', sa.String(),
                              nullable=False, server_default='public'),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_phone'), 'users', ['phone'], unique=True)
    op.create_index(op.f('ix_users_username'),
                    'users', ['username'], unique=True)

    # Create places table
    op.create_table('places',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('name', sa.String(), nullable=False),
                    sa.Column('address', sa.String(), nullable=True),
                    sa.Column('city', sa.String(), nullable=True),
                    sa.Column('neighborhood', sa.String(), nullable=True),
                    sa.Column('latitude', sa.Float(), nullable=True),
                    sa.Column('longitude', sa.Float(), nullable=True),
                    sa.Column('categories', sa.String(), nullable=True),
                    sa.Column('rating', sa.Float(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.Column('external_id', sa.String(), nullable=True),
                    sa.Column('data_source', sa.String(), nullable=True),
                    sa.Column('seed_source', sa.String(),
                              nullable=True, server_default='osm'),
                    sa.Column('website', sa.String(), nullable=True),
                    sa.Column('phone', sa.String(), nullable=True),
                    sa.Column('place_metadata', postgresql.JSONB(
                        astext_type=sa.Text()), nullable=True),
                    sa.Column('fsq_id', sa.String(), nullable=True),
                    sa.Column('osm_id', sa.String(), nullable=True),
                    sa.Column('quality_score', sa.Float(), nullable=True),
                    sa.Column('last_enriched_at', sa.DateTime(
                        timezone=True), nullable=True),
                    sa.Column('discovery_rank', sa.Float(), nullable=True),
                    sa.Column('discovery_score', sa.Float(), nullable=True),
                    sa.Column('discovery_popularity',
                              sa.Float(), nullable=True),
                    sa.Column('discovery_rating', sa.Float(), nullable=True),
                    sa.Column('discovery_price_tier',
                              sa.Integer(), nullable=True),
                    sa.Column('discovery_categories', postgresql.JSONB(
                        astext_type=sa.Text()), nullable=True),
                    sa.Column('discovery_hours', postgresql.JSONB(
                        astext_type=sa.Text()), nullable=True),
                    sa.Column('discovery_photos', postgresql.JSONB(
                        astext_type=sa.Text()), nullable=True),
                    sa.Column('discovery_tips', postgresql.JSONB(
                        astext_type=sa.Text()), nullable=True),
                    sa.Column('discovery_attributes', postgresql.JSONB(
                        astext_type=sa.Text()), nullable=True),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_places_city'), 'places', ['city'], unique=False)
    op.create_index(op.f('ix_places_id'), 'places', ['id'], unique=False)
    op.create_index(op.f('ix_places_name'), 'places', ['name'], unique=False)
    op.create_index(op.f('ix_places_neighborhood'),
                    'places', ['neighborhood'], unique=False)
    op.create_index(op.f('ix_places_external_id'),
                    'places', ['external_id'], unique=False)
    op.create_index(op.f('ix_places_fsq_id'),
                    'places', ['fsq_id'], unique=True)
    op.create_index(op.f('ix_places_osm_id'),
                    'places', ['osm_id'], unique=True)

    # Create check_ins table
    op.create_table('check_ins',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('place_id', sa.Integer(), nullable=False),
                    sa.Column('note', sa.Text(), nullable=True),
                    sa.Column('visibility', sa.String(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.Column('expires_at', sa.DateTime(
                        timezone=True), nullable=False),
                    sa.Column('photo_url', sa.String(), nullable=True),
                    sa.ForeignKeyConstraint(['place_id'], ['places.id'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_check_ins_id'), 'check_ins', ['id'], unique=False)
    op.create_index(op.f('ix_check_ins_place_id'),
                    'check_ins', ['place_id'], unique=False)
    op.create_index(op.f('ix_check_ins_user_id'),
                    'check_ins', ['user_id'], unique=False)

    # Create saved_places table
    op.create_table('saved_places',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('place_id', sa.Integer(), nullable=False),
                    sa.Column('list_name', sa.String(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['place_id'], ['places.id'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_saved_places_id'),
                    'saved_places', ['id'], unique=False)
    op.create_index(op.f('ix_saved_places_place_id'),
                    'saved_places', ['place_id'], unique=False)
    op.create_index(op.f('ix_saved_places_user_id'),
                    'saved_places', ['user_id'], unique=False)

    # Create reviews table
    op.create_table('reviews',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('place_id', sa.Integer(), nullable=False),
                    sa.Column('rating', sa.Float(), nullable=False),
                    sa.Column('text', sa.Text(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['place_id'], ['places.id'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_reviews_id'), 'reviews', ['id'], unique=False)
    op.create_index(op.f('ix_reviews_user_id'),
                    'reviews', ['user_id'], unique=False)
    op.create_index(op.f('ix_reviews_place_id'),
                    'reviews', ['place_id'], unique=False)

    # Create photos table
    op.create_table('photos',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('place_id', sa.Integer(), nullable=False),
                    sa.Column('review_id', sa.Integer(), nullable=True),
                    sa.Column('url', sa.String(), nullable=False),
                    sa.Column('caption', sa.Text(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['place_id'], ['places.id'], ),
                    sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_photos_id'), 'photos', ['id'], unique=False)
    op.create_index(op.f('ix_photos_user_id'),
                    'photos', ['user_id'], unique=False)
    op.create_index(op.f('ix_photos_place_id'),
                    'photos', ['place_id'], unique=False)
    op.create_index(op.f('ix_photos_review_id'),
                    'photos', ['review_id'], unique=False)

    # Create follows table
    op.create_table('follows',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('follower_id', sa.Integer(), nullable=False),
                    sa.Column('followee_id', sa.Integer(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['followee_id'], ['users.id'], ),
                    sa.ForeignKeyConstraint(['follower_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_follows_id'), 'follows', ['id'], unique=False)
    op.create_index(op.f('ix_follows_follower_id'),
                    'follows', ['follower_id'], unique=False)
    op.create_index(op.f('ix_follows_followee_id'),
                    'follows', ['followee_id'], unique=False)

    # Create friendships table
    op.create_table('friendships',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_a_id', sa.Integer(), nullable=False),
                    sa.Column('user_b_id', sa.Integer(), nullable=False),
                    sa.Column('status', sa.String(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.Column('updated_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['user_a_id'], ['users.id'], ),
                    sa.ForeignKeyConstraint(['user_b_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_friendships_id'),
                    'friendships', ['id'], unique=False)
    op.create_index(op.f('ix_friendships_user_a_id'),
                    'friendships', ['user_a_id'], unique=False)
    op.create_index(op.f('ix_friendships_user_b_id'),
                    'friendships', ['user_b_id'], unique=False)

    # Create dm_threads table
    op.create_table('dm_threads',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_a_id', sa.Integer(), nullable=False),
                    sa.Column('user_b_id', sa.Integer(), nullable=False),
                    sa.Column('initiator_id', sa.Integer(), nullable=False),
                    sa.Column('status', sa.String(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.Column('updated_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['initiator_id'], ['users.id'], ),
                    sa.ForeignKeyConstraint(['user_a_id'], ['users.id'], ),
                    sa.ForeignKeyConstraint(['user_b_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_dm_threads_id'),
                    'dm_threads', ['id'], unique=False)
    op.create_index(op.f('ix_dm_threads_user_a_id'),
                    'dm_threads', ['user_a_id'], unique=False)
    op.create_index(op.f('ix_dm_threads_user_b_id'),
                    'dm_threads', ['user_b_id'], unique=False)
    op.create_index(op.f('ix_dm_threads_initiator_id'),
                    'dm_threads', ['initiator_id'], unique=False)

    # Create dm_participant_state table
    op.create_table('dm_participant_state',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('thread_id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('is_typing', sa.Boolean(), nullable=True),
                    sa.Column('typing_until', sa.DateTime(
                        timezone=True), nullable=True),
                    sa.Column('last_read_at', sa.DateTime(
                        timezone=True), nullable=True),
                    sa.Column('is_blocked', sa.Boolean(), nullable=True),
                    sa.ForeignKeyConstraint(
                        ['thread_id'], ['dm_threads.id'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_dm_participant_state_id'),
                    'dm_participant_state', ['id'], unique=False)
    op.create_index(op.f('ix_dm_participant_state_thread_id'),
                    'dm_participant_state', ['thread_id'], unique=False)
    op.create_index(op.f('ix_dm_participant_state_user_id'),
                    'dm_participant_state', ['user_id'], unique=False)

    # Create dm_messages table
    op.create_table('dm_messages',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('thread_id', sa.Integer(), nullable=False),
                    sa.Column('sender_id', sa.Integer(), nullable=False),
                    sa.Column('content', sa.Text(), nullable=False),
                    sa.Column('message_type', sa.String(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.Column('is_pinned', sa.Boolean(), nullable=True),
                    sa.Column('is_archived', sa.Boolean(), nullable=True),
                    sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ),
                    sa.ForeignKeyConstraint(
                        ['thread_id'], ['dm_threads.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_dm_messages_id'),
                    'dm_messages', ['id'], unique=False)
    op.create_index(op.f('ix_dm_messages_thread_id'),
                    'dm_messages', ['thread_id'], unique=False)
    op.create_index(op.f('ix_dm_messages_sender_id'),
                    'dm_messages', ['sender_id'], unique=False)

    # Create dm_message_likes table
    op.create_table('dm_message_likes',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('message_id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(
                        ['message_id'], ['dm_messages.id'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_dm_message_likes_id'),
                    'dm_message_likes', ['id'], unique=False)
    op.create_index(op.f('ix_dm_message_likes_message_id'),
                    'dm_message_likes', ['message_id'], unique=False)
    op.create_index(op.f('ix_dm_message_likes_user_id'),
                    'dm_message_likes', ['user_id'], unique=False)

    # Create check_in_photos table
    op.create_table('check_in_photos',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('check_in_id', sa.Integer(), nullable=False),
                    sa.Column('url', sa.String(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(
                        ['check_in_id'], ['check_ins.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_check_in_photos_id'),
                    'check_in_photos', ['id'], unique=False)
    op.create_index(op.f('ix_check_in_photos_check_in_id'),
                    'check_in_photos', ['check_in_id'], unique=False)

    # Create check_in_comments table
    op.create_table('check_in_comments',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('check_in_id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('content', sa.Text(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.Column('updated_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(
                        ['check_in_id'], ['check_ins.id'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_check_in_comments_id'),
                    'check_in_comments', ['id'], unique=False)
    op.create_index(op.f('ix_check_in_comments_check_in_id'),
                    'check_in_comments', ['check_in_id'], unique=False)
    op.create_index(op.f('ix_check_in_comments_user_id'),
                    'check_in_comments', ['user_id'], unique=False)

    # Create check_in_likes table
    op.create_table('check_in_likes',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('check_in_id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(
                        ['check_in_id'], ['check_ins.id'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_check_in_likes_id'),
                    'check_in_likes', ['id'], unique=False)
    op.create_index(op.f('ix_check_in_likes_check_in_id'),
                    'check_in_likes', ['check_in_id'], unique=False)
    op.create_index(op.f('ix_check_in_likes_user_id'),
                    'check_in_likes', ['user_id'], unique=False)

    # Create otp_codes table
    op.create_table('otp_codes',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=True),
                    sa.Column('phone', sa.String(), nullable=True),
                    sa.Column('code', sa.String(length=6), nullable=False),
                    sa.Column('is_used', sa.Boolean(), nullable=True),
                    sa.Column('expires_at', sa.DateTime(
                        timezone=True), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_otp_codes_id'), 'otp_codes', ['id'], unique=False)
    op.create_index(op.f('ix_otp_codes_phone'),
                    'otp_codes', ['phone'], unique=False)
    op.create_index(op.f('ix_otp_codes_user_id'),
                    'otp_codes', ['user_id'], unique=False)

    # Create support_tickets table
    op.create_table('support_tickets',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('subject', sa.String(), nullable=False),
                    sa.Column('body', sa.Text(), nullable=False),
                    sa.Column('status', sa.String(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.Column('updated_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_support_tickets_id'),
                    'support_tickets', ['id'], unique=False)
    op.create_index(op.f('ix_support_tickets_user_id'),
                    'support_tickets', ['user_id'], unique=False)

    # Create activities table
    op.create_table('activities',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('activity_type', sa.String(), nullable=False),
                    sa.Column('target_id', sa.Integer(), nullable=True),
                    sa.Column('target_type', sa.String(), nullable=True),
                    sa.Column('metadata', postgresql.JSONB(
                        astext_type=sa.Text()), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True),
                              server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_activities_id'),
                    'activities', ['id'], unique=False)
    op.create_index(op.f('ix_activities_user_id'),
                    'activities', ['user_id'], unique=False)

    # Add unique constraints
    op.create_unique_constraint('uq_reviews_user_place', 'reviews', [
                                'user_id', 'place_id'])
    op.create_unique_constraint('uq_saved_places_user_place', 'saved_places', [
                                'user_id', 'place_id'])
    op.create_unique_constraint(
        'uq_dm_message_likes_message_user', 'dm_message_likes', ['message_id', 'user_id'])

    # Add check constraints
    op.create_check_constraint(
        'ck_reviews_rating_range', 'reviews', 'rating >= 0 AND rating <= 5')
    op.create_check_constraint(
        'ck_checkins_visibility', 'check_ins', "visibility IN ('public','friends','private')")


def downgrade() -> None:
    # Drop constraints first
    op.drop_constraint('ck_checkins_visibility', 'check_ins', type_='check')
    op.drop_constraint('ck_reviews_rating_range', 'reviews', type_='check')
    op.drop_constraint('uq_dm_message_likes_message_user',
                       'dm_message_likes', type_='unique')
    op.drop_constraint('uq_saved_places_user_place',
                       'saved_places', type_='unique')
    op.drop_constraint('uq_reviews_user_place', 'reviews', type_='unique')

    # Drop tables in reverse order (respecting foreign key constraints)
    op.drop_index(op.f('ix_activities_user_id'), table_name='activities')
    op.drop_index(op.f('ix_activities_id'), table_name='activities')
    op.drop_table('activities')
    op.drop_index(op.f('ix_support_tickets_user_id'),
                  table_name='support_tickets')
    op.drop_index(op.f('ix_support_tickets_id'), table_name='support_tickets')
    op.drop_table('support_tickets')
    op.drop_index(op.f('ix_otp_codes_user_id'), table_name='otp_codes')
    op.drop_index(op.f('ix_otp_codes_phone'), table_name='otp_codes')
    op.drop_index(op.f('ix_otp_codes_id'), table_name='otp_codes')
    op.drop_table('otp_codes')
    op.drop_index(op.f('ix_check_in_likes_user_id'),
                  table_name='check_in_likes')
    op.drop_index(op.f('ix_check_in_likes_check_in_id'),
                  table_name='check_in_likes')
    op.drop_index(op.f('ix_check_in_likes_id'), table_name='check_in_likes')
    op.drop_table('check_in_likes')
    op.drop_index(op.f('ix_check_in_comments_user_id'),
                  table_name='check_in_comments')
    op.drop_index(op.f('ix_check_in_comments_check_in_id'),
                  table_name='check_in_comments')
    op.drop_index(op.f('ix_check_in_comments_id'),
                  table_name='check_in_comments')
    op.drop_table('check_in_comments')
    op.drop_index(op.f('ix_check_in_photos_check_in_id'),
                  table_name='check_in_photos')
    op.drop_index(op.f('ix_check_in_photos_id'), table_name='check_in_photos')
    op.drop_table('check_in_photos')
    op.drop_index(op.f('ix_dm_message_likes_user_id'),
                  table_name='dm_message_likes')
    op.drop_index(op.f('ix_dm_message_likes_message_id'),
                  table_name='dm_message_likes')
    op.drop_index(op.f('ix_dm_message_likes_id'),
                  table_name='dm_message_likes')
    op.drop_table('dm_message_likes')
    op.drop_index(op.f('ix_dm_messages_sender_id'), table_name='dm_messages')
    op.drop_index(op.f('ix_dm_messages_thread_id'), table_name='dm_messages')
    op.drop_index(op.f('ix_dm_messages_id'), table_name='dm_messages')
    op.drop_table('dm_messages')
    op.drop_index(op.f('ix_dm_participant_state_user_id'),
                  table_name='dm_participant_state')
    op.drop_index(op.f('ix_dm_participant_state_thread_id'),
                  table_name='dm_participant_state')
    op.drop_index(op.f('ix_dm_participant_state_id'),
                  table_name='dm_participant_state')
    op.drop_table('dm_participant_state')
    op.drop_index(op.f('ix_dm_threads_initiator_id'), table_name='dm_threads')
    op.drop_index(op.f('ix_dm_threads_user_b_id'), table_name='dm_threads')
    op.drop_index(op.f('ix_dm_threads_user_a_id'), table_name='dm_threads')
    op.drop_index(op.f('ix_dm_threads_id'), table_name='dm_threads')
    op.drop_table('dm_threads')
    op.drop_index(op.f('ix_friendships_user_b_id'), table_name='friendships')
    op.drop_index(op.f('ix_friendships_user_a_id'), table_name='friendships')
    op.drop_index(op.f('ix_friendships_id'), table_name='friendships')
    op.drop_table('friendships')
    op.drop_index(op.f('ix_follows_followee_id'), table_name='follows')
    op.drop_index(op.f('ix_follows_follower_id'), table_name='follows')
    op.drop_index(op.f('ix_follows_id'), table_name='follows')
    op.drop_table('follows')
    op.drop_index(op.f('ix_photos_review_id'), table_name='photos')
    op.drop_index(op.f('ix_photos_place_id'), table_name='photos')
    op.drop_index(op.f('ix_photos_user_id'), table_name='photos')
    op.drop_index(op.f('ix_photos_id'), table_name='photos')
    op.drop_table('photos')
    op.drop_index(op.f('ix_reviews_place_id'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_user_id'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_id'), table_name='reviews')
    op.drop_table('reviews')
    op.drop_index(op.f('ix_saved_places_user_id'), table_name='saved_places')
    op.drop_index(op.f('ix_saved_places_place_id'), table_name='saved_places')
    op.drop_index(op.f('ix_saved_places_id'), table_name='saved_places')
    op.drop_table('saved_places')
    op.drop_index(op.f('ix_check_ins_user_id'), table_name='check_ins')
    op.drop_index(op.f('ix_check_ins_place_id'), table_name='check_ins')
    op.drop_index(op.f('ix_check_ins_id'), table_name='check_ins')
    op.drop_table('check_ins')
    op.drop_index(op.f('ix_places_osm_id'), table_name='places')
    op.drop_index(op.f('ix_places_foursquare_id'), table_name='places')
    op.drop_index(op.f('ix_places_neighborhood'), table_name='places')
    op.drop_index(op.f('ix_places_name'), table_name='places')
    op.drop_index(op.f('ix_places_id'), table_name='places')
    op.drop_index(op.f('ix_places_city'), table_name='places')
    op.drop_table('places')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_phone'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
