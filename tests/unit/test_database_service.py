"""
Unit tests for Database Service
"""
from app.models import User, Place, UserCollection
from app.database import AsyncSessionLocal, get_db
import asyncio
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../app'))


class DatabaseServiceTest:
    """Test Database Service functionality"""

    def __init__(self):
        pass

    def test_database_connection(self):
        """Test database connection"""
        # Test that we can import the database components
        from app.database import AsyncSessionLocal, get_db

        assert AsyncSessionLocal is not None
        assert get_db is not None

        print("✅ Database connection test passed")

    def test_model_imports(self):
        """Test that all models can be imported"""
        from app.models import (
            User, Place, UserCollection, UserCollectionPlace,
            CheckIn, Photo, DMThread, DMThreadParticipant
        )

        # Test that models are properly defined
        assert User is not None
        assert Place is not None
        assert UserCollection is not None
        assert UserCollectionPlace is not None
        assert CheckIn is not None
        assert Photo is not None
        assert DMThread is not None

        print("✅ Model imports test passed")

    def test_user_model_fields(self):
        """Test User model field definitions"""
        from app.models import User

        # Test that User model has expected fields
        user_fields = User.__table__.columns.keys()

        expected_fields = [
            'id', 'phone', 'username', 'name', 'email', 'is_verified',
            'is_admin', 'bio', 'avatar_url', 'dm_privacy',
            'checkins_default_visibility', 'collections_default_visibility',
            'profile_visibility', 'follower_list_visibility',
            'following_list_visibility', 'stats_visibility',
            'media_default_visibility', 'search_visibility',
            'availability_status', 'availability_mode'
        ]

        for field in expected_fields:
            assert field in user_fields, f"Field {field} not found in User model"

        print("✅ User model fields test passed")

    def test_place_model_fields(self):
        """Test Place model field definitions"""
        from app.models import Place

        # Test that Place model has expected fields
        place_fields = Place.__table__.columns.keys()

        expected_fields = [
            'id', 'name', 'address', 'city', 'country', 'neighborhood',
            'latitude', 'longitude', 'categories', 'rating', 'price_tier',
            'description', 'photo_url', 'external_id', 'data_source'
        ]

        for field in expected_fields:
            assert field in place_fields, f"Field {field} not found in Place model"

        print("✅ Place model fields test passed")

    def test_collection_model_fields(self):
        """Test UserCollection model field definitions"""
        from app.models import UserCollection

        # Test that UserCollection model has expected fields
        collection_fields = UserCollection.__table__.columns.keys()

        expected_fields = [
            'id', 'user_id', 'name', 'description', 'is_public',
            'visibility', 'created_at', 'updated_at'
        ]

        for field in expected_fields:
            assert field in collection_fields, f"Field {field} not found in UserCollection model"

        print("✅ Collection model fields test passed")

    def test_model_relationships(self):
        """Test model relationships"""
        from app.models import User, Place, UserCollection, CheckIn

        # Test User relationships
        user = User()
        assert hasattr(user, 'check_ins')
        assert hasattr(user, 'saved_places')
        assert hasattr(user, 'reviews')
        assert hasattr(user, 'collections')

        # Test Place relationships
        place = Place()
        assert hasattr(place, 'check_ins')
        assert hasattr(place, 'photos')
        assert hasattr(place, 'reviews')

        # Test Collection relationships
        collection = UserCollection()
        assert hasattr(collection, 'places')

        print("✅ Model relationships test passed")

    def test_model_defaults(self):
        """Test model default values"""
        from app.models import User, CheckIn, DMThread

        # Test User defaults
        user = User()
        assert user.is_verified is False
        assert user.is_admin is False
        assert user.dm_privacy == "everyone"
        assert user.checkins_default_visibility == "private"
        assert user.collections_default_visibility == "public"
        assert user.profile_visibility == "public"
        assert user.availability_status == "not_available"
        assert user.availability_mode == "auto"

        # Test CheckIn defaults
        checkin = CheckIn()
        assert checkin.visibility == "public"

        # Test DMThread defaults
        thread = DMThread()
        assert thread.status == "pending"

        print("✅ Model defaults test passed")

    def test_model_validation(self):
        """Test model validation"""
        from app.models import User, Place

        # Test User validation
        user = User(phone="+1234567890")
        assert user.phone == "+1234567890"

        # Test Place validation
        place = Place(
            name="Test Place",
            latitude=40.7128,
            longitude=-74.0060
        )
        assert place.name == "Test Place"
        assert place.latitude == 40.7128
        assert place.longitude == -74.0060

        print("✅ Model validation test passed")

    def test_database_configuration(self):
        """Test database configuration"""
        import os

        # Test that database URL is configured
        db_url = os.getenv('DATABASE_URL')
        assert db_url is not None
        assert len(db_url) > 0

        # Test that it's a valid SQLite URL for testing
        assert 'sqlite' in db_url.lower()

        print("✅ Database configuration test passed")

    def test_async_session_creation(self):
        """Test async session creation"""
        from app.database import AsyncSessionLocal

        # Test that we can create a session (without actually using it)
        session = AsyncSessionLocal()
        assert session is not None

        print("✅ Async session creation test passed")

    def test_model_table_names(self):
        """Test model table names"""
        from app.models import User, Place, UserCollection, CheckIn, Photo, DMThread

        # Test table names
        assert User.__tablename__ == "users"
        assert Place.__tablename__ == "places"
        assert UserCollection.__tablename__ == "user_collections"
        assert CheckIn.__tablename__ == "check_ins"
        assert Photo.__tablename__ == "photos"
        assert DMThread.__tablename__ == "dm_threads"

        print("✅ Model table names test passed")

    def test_model_primary_keys(self):
        """Test model primary keys"""
        from app.models import User, Place, UserCollection

        # Test primary key fields
        assert User.id.primary_key is True
        assert Place.id.primary_key is True
        assert UserCollection.id.primary_key is True

        print("✅ Model primary keys test passed")

    def test_model_foreign_keys(self):
        """Test model foreign keys"""
        from app.models import UserCollection, CheckIn

        # Test foreign key relationships
        assert UserCollection.user_id.foreign_keys is not None
        assert CheckIn.user_id.foreign_keys is not None
        assert CheckIn.place_id.foreign_keys is not None

        print("✅ Model foreign keys test passed")

    def run_all_tests(self):
        """Run all database service tests"""
        print("🗄️ Testing Database Service...")
        print("=" * 50)

        try:
            self.test_database_connection()
            self.test_model_imports()
            self.test_user_model_fields()
            self.test_place_model_fields()
            self.test_collection_model_fields()
            self.test_model_relationships()
            self.test_model_defaults()
            self.test_model_validation()
            self.test_database_configuration()
            self.test_async_session_creation()
            self.test_model_table_names()
            self.test_model_primary_keys()
            self.test_model_foreign_keys()

            print("\n✅ All Database Service tests passed!")

        except Exception as e:
            print(f"\n❌ Database Service test failed: {e}")
            raise


async def main():
    """Main test runner"""
    test = DatabaseServiceTest()
    test.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
