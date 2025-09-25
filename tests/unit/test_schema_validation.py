"""Unit tests for schema validation to prevent runtime errors."""

import pytest
from datetime import datetime, timezone
from app.schemas import (
    PublicUserResponse,
    EnhancedPlaceResponse,
    PlaceStats,
    CollectionResponse,
    CheckInResponse
)


class TestPublicUserResponseSchema:
    """Test PublicUserResponse schema validation."""

    def test_public_user_response_valid_data(self):
        """Test PublicUserResponse with valid data."""
        valid_data = {
            "id": 1,
            "name": "Test User",
            "username": "testuser",
            "bio": "Test bio",
            "avatar_url": "https://example.com/avatar.jpg",
            "availability_status": "available",
            "availability_mode": "auto",
            "created_at": datetime.now(timezone.utc),
            "followers_count": 10,
            "following_count": 5,
            "check_ins_count": 25,
            "is_followed": False,
            "is_blocked": False
        }

        user_response = PublicUserResponse(**valid_data)
        assert user_response.id == 1
        assert user_response.name == "Test User"
        assert user_response.username == "testuser"
        assert user_response.followers_count == 10
        assert user_response.is_followed is False

    def test_public_user_response_missing_required_fields(self):
        """Test PublicUserResponse with missing required fields."""
        invalid_data = {
            "id": 1,
            "name": "Test User",
            # Missing required fields
        }

        with pytest.raises(ValueError):
            PublicUserResponse(**invalid_data)

    def test_public_user_response_invalid_enum_values(self):
        """Test PublicUserResponse with invalid enum values."""
        invalid_data = {
            "id": 1,
            "name": "Test User",
            "username": "testuser",
            "availability_status": "invalid_status",  # Invalid enum value
            "availability_mode": "auto",
            "created_at": datetime.now(timezone.utc),
            "followers_count": 10,
            "following_count": 5,
            "check_ins_count": 25,
            "is_followed": False,
            "is_blocked": False
        }

        with pytest.raises(ValueError):
            PublicUserResponse(**invalid_data)


class TestPlaceStatsSchema:
    """Test PlaceStats schema validation."""

    def test_place_stats_valid_data(self):
        """Test PlaceStats with valid data."""
        valid_data = {
            "place_id": 1,
            "average_rating": 4.5,
            "reviews_count": 10,
            "active_checkins": 5
        }

        place_stats = PlaceStats(**valid_data)
        assert place_stats.place_id == 1
        assert place_stats.average_rating == 4.5
        assert place_stats.reviews_count == 10
        assert place_stats.active_checkins == 5

    def test_place_stats_missing_required_fields(self):
        """Test PlaceStats with missing required fields."""
        invalid_data = {
            "place_id": 1,
            # Missing required fields
        }

        with pytest.raises(ValueError):
            PlaceStats(**invalid_data)


class TestEnhancedPlaceResponseSchema:
    """Test EnhancedPlaceResponse schema validation."""

    def test_enhanced_place_response_valid_data(self):
        """Test EnhancedPlaceResponse with valid data."""
        place_stats = PlaceStats(
            place_id=1,
            average_rating=4.5,
            reviews_count=10,
            active_checkins=5
        )

        valid_data = {
            "id": 1,
            "name": "Test Place",
            "address": "123 Test St",
            "country": "US",
            "city": "Test City",
            "neighborhood": "Test Neighborhood",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "categories": "restaurant,food",
            "rating": 4.5,
            "description": "A test place",
            "price_tier": "$$",
            "created_at": datetime.now(timezone.utc),
            "stats": place_stats,
            "current_checkins": 5,
            "total_checkins": 25,
            "recent_reviews": 3,
            "photos_count": 10,
            "is_checked_in": False,
        }

        place_response = EnhancedPlaceResponse(**valid_data)
        assert place_response.id == 1
        assert place_response.name == "Test Place"
        assert place_response.stats.place_id == 1
        assert place_response.current_checkins == 5

    def test_enhanced_place_response_missing_required_fields(self):
        """Test EnhancedPlaceResponse with missing required fields."""
        invalid_data = {
            "id": 1,
            "name": "Test Place",
            # Missing required fields like stats, current_checkins, etc.
        }

        with pytest.raises(ValueError):
            EnhancedPlaceResponse(**invalid_data)


class TestCollectionResponseSchema:
    """Test CollectionResponse schema validation."""

    def test_collection_response_valid_data(self):
        """Test CollectionResponse with valid data."""
        valid_data = {
            "id": 1,
            "user_id": 2,
            "name": "Test Collection",
            "description": "A test collection",
            "is_public": True,
            "visibility": "public",
            "created_at": datetime.now(timezone.utc)
        }

        collection_response = CollectionResponse(**valid_data)
        assert collection_response.id == 1
        assert collection_response.user_id == 2
        assert collection_response.name == "Test Collection"
        assert collection_response.is_public is True
        assert collection_response.visibility == "public"

    def test_collection_response_invalid_visibility(self):
        """Test CollectionResponse with invalid visibility."""
        invalid_data = {
            "id": 1,
            "user_id": 2,
            "name": "Test Collection",
            "description": "A test collection",
            "is_public": True,
            "visibility": "invalid_visibility",  # Invalid enum value
            "created_at": datetime.now(timezone.utc)
        }

        with pytest.raises(ValueError):
            CollectionResponse(**invalid_data)


class TestCheckInResponseSchema:
    """Test CheckInResponse schema validation."""

    def test_check_in_response_valid_data(self):
        """Test CheckInResponse with valid data."""
        valid_data = {
            "id": 1,
            "user_id": 2,
            "place_id": 3,
            "note": "Great place!",
            "visibility": "public",
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc),
            "latitude": 37.7749,
            "longitude": -122.4194,
            "photo_url": "https://example.com/photo.jpg",
            "photo_urls": ["https://example.com/photo.jpg"],
            "allowed_to_chat": True
        }

        checkin_response = CheckInResponse(**valid_data)
        assert checkin_response.id == 1
        assert checkin_response.user_id == 2
        assert checkin_response.place_id == 3
        assert checkin_response.note == "Great place!"
        assert checkin_response.allowed_to_chat is True

    def test_check_in_response_missing_required_fields(self):
        """Test CheckInResponse with missing required fields."""
        invalid_data = {
            "id": 1,
            "user_id": 2,
            # Missing required fields like place_id, visibility, etc.
        }

        with pytest.raises(ValueError):
            CheckInResponse(**invalid_data)


class TestSchemaFieldTypes:
    """Test schema field type validation."""

    def test_public_user_response_field_types(self):
        """Test PublicUserResponse field types."""
        valid_data = {
            "id": 1,
            "name": "Test User",
            "username": "testuser",
            "bio": "Test bio",
            "avatar_url": "https://example.com/avatar.jpg",
            "availability_status": "available",
            "availability_mode": "auto",
            "created_at": datetime.now(timezone.utc),
            "followers_count": 10,
            "following_count": 5,
            "check_ins_count": 25,
            "is_followed": False,
            "is_blocked": False
        }

        user_response = PublicUserResponse(**valid_data)

        # Test field types
        assert isinstance(user_response.id, int)
        assert isinstance(user_response.name, str)
        assert isinstance(user_response.followers_count, int)
        assert isinstance(user_response.is_followed, bool)
        assert isinstance(user_response.created_at, datetime)

    def test_enhanced_place_response_field_types(self):
        """Test EnhancedPlaceResponse field types."""
        place_stats = PlaceStats(
            place_id=1,
            average_rating=4.5,
            reviews_count=10,
            active_checkins=5
        )

        valid_data = {
            "id": 1,
            "name": "Test Place",
            "address": "123 Test St",
            "country": "US",
            "city": "Test City",
            "neighborhood": "Test Neighborhood",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "categories": "restaurant,food",
            "rating": 4.5,
            "description": "A test place",
            "price_tier": "$$",
            "created_at": datetime.now(timezone.utc),
            "stats": place_stats,
            "current_checkins": 5,
            "total_checkins": 25,
            "recent_reviews": 3,
            "photos_count": 10,
            "is_checked_in": False,
        }

        place_response = EnhancedPlaceResponse(**valid_data)

        # Test field types
        assert isinstance(place_response.id, int)
        assert isinstance(place_response.name, str)
        assert isinstance(place_response.latitude, float)
        assert isinstance(place_response.longitude, float)
        assert isinstance(place_response.current_checkins, int)
        assert isinstance(place_response.is_checked_in, bool)
        assert isinstance(place_response.stats, PlaceStats)
