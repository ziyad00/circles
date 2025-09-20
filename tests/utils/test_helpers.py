"""
Test helper functions and utilities
"""
from sqlalchemy import select
from app.models import User, Place, UserCollection, UserCollectionPlace
from app.database import AsyncSessionLocal
import asyncio
import os
import sys
from typing import Dict, Any, Optional, List
import json

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../app'))


class TestDataFactory:
    """Factory for creating test data"""

    @staticmethod
    async def create_test_places(count: int = 5) -> List[Place]:
        """Create test places"""
        places = []
        async with AsyncSessionLocal() as db:
            for i in range(count):
                place = Place(
                    name=f"Test Place {i+1}",
                    address=f"{100+i} Test St",
                    city="Test City",
                    latitude=40.7128 + (i * 0.01),
                    longitude=-74.0060 + (i * 0.01),
                    categories=f"test,category{i+1}"
                )
                db.add(place)
                places.append(place)

            await db.commit()
            for place in places:
                await db.refresh(place)

        return places

    @staticmethod
    async def create_test_collection(user_id: int, name: str = "Test Collection") -> UserCollection:
        """Create test collection"""
        async with AsyncSessionLocal() as db:
            collection = UserCollection(
                user_id=user_id,
                name=name,
                description="Test collection description",
                is_public=True
            )
            db.add(collection)
            await db.commit()
            await db.refresh(collection)
            return collection

    @staticmethod
    async def add_places_to_collection(collection_id: int, place_ids: List[int]):
        """Add places to collection"""
        async with AsyncSessionLocal() as db:
            for place_id in place_ids:
                collection_place = UserCollectionPlace(
                    collection_id=collection_id,
                    place_id=place_id
                )
                db.add(collection_place)
            await db.commit()


class TestAssertions:
    """Test assertion helpers"""

    @staticmethod
    def assert_response_success(response, expected_status: int = 200):
        """Assert response is successful"""
        assert response.status_code == expected_status, \
            f"Expected status {expected_status}, got {response.status_code}: {response.text}"

    @staticmethod
    def assert_response_error(response, expected_status: int):
        """Assert response is an error"""
        assert response.status_code == expected_status, \
            f"Expected error status {expected_status}, got {response.status_code}: {response.text}"

    @staticmethod
    def assert_json_contains(response, key: str, expected_value: Any = None):
        """Assert JSON response contains key and optionally value"""
        data = response.json
        assert key in data, f"Key '{key}' not found in response: {data}"

        if expected_value is not None:
            assert data[key] == expected_value, \
                f"Expected {key}={expected_value}, got {data[key]}"

    @staticmethod
    def assert_json_structure(response, expected_keys: List[str]):
        """Assert JSON response has expected structure"""
        data = response.json
        for key in expected_keys:
            assert key in data, f"Missing key '{key}' in response: {list(data.keys())}"

    @staticmethod
    def assert_pagination(response, expected_keys: List[str] = None):
        """Assert response has pagination structure"""
        if expected_keys is None:
            expected_keys = ['items', 'total', 'limit', 'offset']

        TestAssertions.assert_json_structure(response, expected_keys)

        data = response.json
        assert isinstance(data['items'], list), "Items should be a list"
        assert isinstance(data['total'], int), "Total should be an integer"
        assert isinstance(data['limit'], int), "Limit should be an integer"
        assert isinstance(data['offset'], int), "Offset should be an integer"


class TestCleanup:
    """Test cleanup utilities"""

    @staticmethod
    async def cleanup_test_data():
        """Clean up all test data"""
        async with AsyncSessionLocal() as db:
            # Delete test collections
            await db.execute("DELETE FROM user_collection_places WHERE collection_id IN (SELECT id FROM user_collections WHERE name LIKE 'Test%')")
            await db.execute("DELETE FROM user_collections WHERE name LIKE 'Test%'")

            # Delete test places
            await db.execute("DELETE FROM places WHERE name LIKE 'Test%'")

            # Delete test user (optional - might want to keep for other tests)
            # await db.execute("DELETE FROM users WHERE phone = '+1234567890'")

            await db.commit()


class TestFixtures:
    """Test fixtures and sample data"""

    SAMPLE_PLACE = {
        "name": "Sample Coffee Shop",
        "address": "123 Main St",
        "city": "Sample City",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "categories": "coffee,cafe"
    }

    SAMPLE_COLLECTION = {
        "name": "Sample Collection",
        "description": "A sample collection for testing",
        "is_public": True
    }

    SAMPLE_USER_UPDATE = {
        "name": "Updated Test User",
        "bio": "Updated bio for testing"
    }

    @staticmethod
    def get_sample_place_data(variation: int = 0) -> Dict[str, Any]:
        """Get sample place data with variation"""
        data = TestFixtures.SAMPLE_PLACE.copy()
        data["name"] = f"{data['name']} {variation}"
        data["latitude"] += variation * 0.01
        data["longitude"] += variation * 0.01
        return data

    @staticmethod
    def get_sample_collection_data(variation: int = 0) -> Dict[str, Any]:
        """Get sample collection data with variation"""
        data = TestFixtures.SAMPLE_COLLECTION.copy()
        data["name"] = f"{data['name']} {variation}"
        return data
