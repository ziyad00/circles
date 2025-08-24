#!/usr/bin/env python3
"""
Migration Sequence Test Script
Tests the complete migration sequence against a fresh database
"""

from app.models import Base
from app.database import get_db
from sqlalchemy import text
import asyncio
import logging
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_migration_sequence():
    """Test the complete migration sequence"""
    logger.info("🚀 Starting Migration Sequence Test")

    try:
        # Get database connection
        async for db in get_db():
            logger.info("✅ Database connection established")

            # Test 1: Check if all tables exist
            logger.info("📋 Test 1: Verifying all tables exist")
            tables_to_check = [
                'users', 'places', 'check_ins', 'saved_places', 'reviews',
                'photos', 'follows', 'dm_threads', 'dm_participant_states',
                'dm_messages', 'dm_message_likes', 'check_in_photos',
                'check_in_comments', 'check_in_likes', 'otp_codes',
                'support_tickets', 'activities', 'user_interests',
                'notification_preferences', 'check_in_collections',
                'check_in_collection_items'
            ]

            for table_name in tables_to_check:
                result = await db.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"))
                exists = result.scalar()
                if exists:
                    logger.info(f"   ✅ Table '{table_name}' exists")
                else:
                    logger.error(f"   ❌ Table '{table_name}' missing")
                    return False

            # Test 2: Check if key columns exist in places table
            logger.info("📋 Test 2: Verifying places table structure")
            places_columns = [
                'id', 'name', 'address', 'city', 'neighborhood', 'latitude',
                'longitude', 'categories', 'rating', 'created_at', 'external_id',
                'data_source', 'fsq_id', 'seed_source', 'website', 'phone',
                'place_metadata', 'last_enriched_at'
            ]

            for column in places_columns:
                result = await db.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'places' AND column_name = '{column}')"))
                exists = result.scalar()
                if exists:
                    logger.info(
                        f"   ✅ Column '{column}' exists in places table")
                else:
                    logger.error(
                        f"   ❌ Column '{column}' missing from places table")
                    return False

            # Test 3: Check if indexes exist
            logger.info("📋 Test 3: Verifying key indexes")
            indexes_to_check = [
                ('places', 'ix_places_fsq_id'),
                ('places', 'ix_places_external_id'),
                ('users', 'ix_users_email'),
                ('users', 'ix_users_phone'),
                ('users', 'ix_users_username')
            ]

            for table, index in indexes_to_check:
                result = await db.execute(text(f"SELECT EXISTS (SELECT FROM pg_indexes WHERE tablename = '{table}' AND indexname = '{index}')"))
                exists = result.scalar()
                if exists:
                    logger.info(f"   ✅ Index '{index}' exists on '{table}'")
                else:
                    logger.error(
                        f"   ❌ Index '{index}' missing from '{table}'")
                    return False

            # Test 4: Check if constraints exist
            logger.info("📋 Test 4: Verifying key constraints")
            constraints_to_check = [
                ('uq_dm_message_like_user', 'dm_message_likes'),
                ('uq_checkin_like', 'check_in_likes')
            ]

            for constraint, table in constraints_to_check:
                result = await db.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.table_constraints WHERE constraint_name = '{constraint}' AND table_name = '{table}')"))
                exists = result.scalar()
                if exists:
                    logger.info(
                        f"   ✅ Constraint '{constraint}' exists on '{table}'")
                else:
                    logger.error(
                        f"   ❌ Constraint '{constraint}' missing from '{table}'")
                    return False

            # Test 5: Check if foreign keys exist
            logger.info("📋 Test 5: Verifying foreign key relationships")
            fk_to_check = [
                ('check_ins', 'user_id', 'users', 'id'),
                ('check_ins', 'place_id', 'places', 'id'),
                ('reviews', 'user_id', 'users', 'id'),
                ('reviews', 'place_id', 'places', 'id'),
                ('follows', 'follower_id', 'users', 'id'),
                ('follows', 'followee_id', 'users', 'id')
            ]

            for table, fk_column, ref_table, ref_column in fk_to_check:
                result = await db.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.key_column_usage kcu
                        JOIN information_schema.table_constraints tc ON kcu.constraint_name = tc.constraint_name
                        WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND kcu.table_name = '{table}'
                        AND kcu.column_name = '{fk_column}'
                        AND kcu.referenced_table_name = '{ref_table}'
                        AND kcu.referenced_column_name = '{ref_column}'
                    )
                """))
                exists = result.scalar()
                if exists:
                    logger.info(
                        f"   ✅ FK {table}.{fk_column} -> {ref_table}.{ref_column}")
                else:
                    logger.error(
                        f"   ❌ FK {table}.{fk_column} -> {ref_table}.{ref_column} missing")
                    return False

            # Test 6: Check if seeded data exists
            logger.info("📋 Test 6: Verifying seeded data")
            result = await db.execute(text("SELECT COUNT(*) FROM places WHERE data_source = 'osm_overpass'"))
            count = result.scalar()
            if count > 0:
                logger.info(f"   ✅ Found {count} seeded places from OSM")
            else:
                logger.warning(
                    f"   ⚠️  No seeded places found (count: {count})")

            # Test 7: Check if we can insert test data
            logger.info("📋 Test 7: Testing data insertion")
            try:
                # Test user insertion
                result = await db.execute(text("""
                    INSERT INTO users (email, phone, username, is_verified, name)
                    VALUES ('test@example.com', '+1234567890', 'testuser', true, 'Test User')
                    RETURNING id
                """))
                user_id = result.scalar()
                logger.info(f"   ✅ Test user created with ID: {user_id}")

                # Test place insertion
                result = await db.execute(text("""
                    INSERT INTO places (name, latitude, longitude, categories, data_source)
                    VALUES ('Test Place', 24.7136, 46.6753, 'test:category', 'test')
                    RETURNING id
                """))
                place_id = result.scalar()
                logger.info(f"   ✅ Test place created with ID: {place_id}")

                # Test check-in insertion
                result = await db.execute(text(f"""
                    INSERT INTO check_ins (user_id, place_id, latitude, longitude, expires_at)
                    VALUES ({user_id}, {place_id}, 24.7136, 46.6753, NOW() + INTERVAL '24 hours')
                    RETURNING id
                """))
                checkin_id = result.scalar()
                logger.info(
                    f"   ✅ Test check-in created with ID: {checkin_id}")

                # Clean up test data
                await db.execute(text(f"DELETE FROM check_ins WHERE id = {checkin_id}"))
                await db.execute(text(f"DELETE FROM places WHERE id = {place_id}"))
                await db.execute(text(f"DELETE FROM users WHERE id = {user_id}"))
                await db.commit()
                logger.info("   ✅ Test data cleaned up")

            except Exception as e:
                logger.error(f"   ❌ Data insertion test failed: {e}")
                return False

            logger.info("🎉 All migration tests passed!")
            return True

    except Exception as e:
        logger.error(f"❌ Migration test failed: {e}")
        return False


async def main():
    """Main test function"""
    logger.info("=" * 60)
    logger.info("MIGRATION SEQUENCE VERIFICATION TEST")
    logger.info("=" * 60)

    success = await test_migration_sequence()

    logger.info("=" * 60)
    if success:
        logger.info(
            "✅ ALL TESTS PASSED - Migration sequence is working correctly!")
        sys.exit(0)
    else:
        logger.error("❌ TESTS FAILED - Migration sequence has issues!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
