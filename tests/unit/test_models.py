"""
Unit tests for Database Models
"""
from app.models import User, Place, UserCollection, UserCollectionPlace, CheckIn, Photo, DMThread
import asyncio
import os
import sys
from datetime import datetime

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../app'))


class ModelsTest:
    """Test Database Models functionality"""

    def __init__(self):
        pass

    def test_user_model(self):
        """Test User model creation and validation"""
        user = User(
            phone="+1234567890",
            username="testuser",
            name="Test User",
            email="test@example.com",
            is_verified=True
        )

        assert user.phone == "+1234567890"
        assert user.username == "testuser"
        assert user.name == "Test User"
        assert user.email == "test@example.com"
        assert user.is_verified is True
        assert user.is_admin is False  # Default value

        print("✅ User model test passed")

    def test_place_model(self):
        """Test Place model creation and validation"""
        place = Place(
            name="Test Place",
            address="123 Test St",
            city="Test City",
            latitude=40.7128,
            longitude=-74.0060,
            categories="coffee,cafe"
        )

        assert place.name == "Test Place"
        assert place.address == "123 Test St"
        assert place.city == "Test City"
        assert place.latitude == 40.7128
        assert place.longitude == -74.0060
        assert place.categories == "coffee,cafe"

        print("✅ Place model test passed")

    def test_user_collection_model(self):
        """Test UserCollection model creation and validation"""
        collection = UserCollection(
            user_id=1,
            name="Test Collection",
            description="A test collection",
            is_public=True
        )

        assert collection.user_id == 1
        assert collection.name == "Test Collection"
        assert collection.description == "A test collection"
        assert collection.is_public is True

        print("✅ UserCollection model test passed")

    def test_user_collection_place_model(self):
        """Test UserCollectionPlace model creation and validation"""
        collection_place = UserCollectionPlace(
            collection_id=1,
            place_id=1
        )

        assert collection_place.collection_id == 1
        assert collection_place.place_id == 1

        print("✅ UserCollectionPlace model test passed")

    def test_checkin_model(self):
        """Test CheckIn model creation and validation"""
        checkin = CheckIn(
            user_id=1,
            place_id=1,
            text="Great coffee!",
            visibility="public"
        )

        assert checkin.user_id == 1
        assert checkin.place_id == 1
        assert checkin.text == "Great coffee!"
        assert checkin.visibility == "public"

        print("✅ CheckIn model test passed")

    def test_photo_model(self):
        """Test Photo model creation and validation"""
        photo = Photo(
            url="https://example.com/photo.jpg",
            user_id=1,
            place_id=1,
            checkin_id=1
        )

        assert photo.url == "https://example.com/photo.jpg"
        assert photo.user_id == 1
        assert photo.place_id == 1
        assert photo.checkin_id == 1

        print("✅ Photo model test passed")

    def test_dm_thread_model(self):
        """Test DMThread model creation and validation"""
        thread = DMThread(
            user_a_id=1,
            user_b_id=2,
            initiator_id=1,
            status="accepted"
        )

        assert thread.user_a_id == 1
        assert thread.user_b_id == 2
        assert thread.initiator_id == 1
        assert thread.status == "accepted"

        print("✅ DMThread model test passed")

    def test_model_relationships(self):
        """Test model relationships"""
        # Test that relationships are properly defined
        user = User()
        assert hasattr(user, 'check_ins')
        assert hasattr(user, 'saved_places')
        assert hasattr(user, 'reviews')
        assert hasattr(user, 'collections')

        place = Place()
        assert hasattr(place, 'check_ins')
        assert hasattr(place, 'photos')
        assert hasattr(place, 'reviews')

        collection = UserCollection()
        assert hasattr(collection, 'places')

        print("✅ Model relationships test passed")

    def test_model_defaults(self):
        """Test model default values"""
        user = User()
        assert user.is_verified is False
        assert user.is_admin is False
        assert user.dm_privacy == "everyone"
        assert user.checkins_default_visibility == "private"
        assert user.collections_default_visibility == "public"
        assert user.profile_visibility == "public"
        assert user.availability_status == "not_available"
        assert user.availability_mode == "auto"

        checkin = CheckIn()
        assert checkin.visibility == "public"

        thread = DMThread()
        assert thread.status == "pending"

        print("✅ Model defaults test passed")

    def test_model_validation(self):
        """Test model validation constraints"""
        # Test required fields
        try:
            user = User()  # Should work with defaults
            assert user is not None
        except Exception as e:
            print(f"User creation failed: {e}")
            raise

        # Test that we can set required fields
        user = User(phone="+1234567890")
        assert user.phone == "+1234567890"

        print("✅ Model validation test passed")

    def run_all_tests(self):
        """Run all model tests"""
        print("🗄️ Testing Database Models...")
        print("=" * 50)

        try:
            self.test_user_model()
            self.test_place_model()
            self.test_user_collection_model()
            self.test_user_collection_place_model()
            self.test_checkin_model()
            self.test_photo_model()
            self.test_dm_thread_model()
            self.test_model_relationships()
            self.test_model_defaults()
            self.test_model_validation()

            print("\n✅ All Database Models tests passed!")

        except Exception as e:
            print(f"\n❌ Database Models test failed: {e}")
            raise


async def main():
    """Main test runner"""
    test = ModelsTest()
    test.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
