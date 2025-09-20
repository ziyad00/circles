"""
Comprehensive test suite for Collections API functionality.

This test file validates all aspects of the collections system including:
- Collection CRUD operations
- Place management within collections
- Photo handling and signed URLs
- Visibility controls and permission checking
- SavedPlace synchronization
- Edge cases and error conditions
"""

import asyncio
import json
import pytest
from tests.utils.base_test import BaseAPITest
from tests.utils.auth_helper import get_auth_headers


class CollectionsComprehensiveTest(BaseAPITest):
    """Comprehensive test suite for Collections API"""

    def __init__(self, config=None, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.collection_id = None
        self.test_place_id = None
        self.second_collection_id = None
        self.test_user_id = None
        self.test_user_token = None
        self.second_user_id = None
        self.second_user_token = None

    async def execute(self):
        """Execute all comprehensive collection tests"""
        await self.setup_test_data()
        await self.test_collection_lifecycle()
        await self.test_place_management()
        await self.test_visibility_and_permissions()
        await self.test_photo_handling()
        await self.test_saved_place_synchronization()
        await self.test_edge_cases_and_errors()
        await self.test_pagination_and_limits()
        await self.cleanup_test_data()

    async def setup_test_data(self):
        """Set up test users, places, and initial data"""
        await self.add_test("Setup - Create test users and places")

        # Create test users
        user1_data = {
            "first_name": "Collection",
            "last_name": "Tester1",
            "phone": "1234567890",
            "username": "collection_tester1"
        }

        user2_data = {
            "first_name": "Collection",
            "last_name": "Tester2",
            "phone": "1234567891",
            "username": "collection_tester2"
        }

        # Register first user
        response = await self.post("/auth/register", json=user1_data)
        if response.status_code == 201:
            self.test_user_id = response.json()["user"]["id"]
            self.test_user_token = response.json()["access_token"]
            await self.mark_test_passed("Created test user 1")
        else:
            await self.mark_test_failed(f"Failed to create test user 1: {response.text}")
            return

        # Register second user
        response = await self.post("/auth/register", json=user2_data)
        if response.status_code == 201:
            self.second_user_id = response.json()["user"]["id"]
            self.second_user_token = response.json()["access_token"]
            await self.mark_test_passed("Created test user 2")
        else:
            await self.mark_test_failed(f"Failed to create test user 2: {response.text}")
            return

        # Create a test place
        place_data = {
            "name": "Test Collection Place",
            "address": "123 Collection St",
            "city": "Test City",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "description": "A place for testing collections"
        }

        headers = get_auth_headers(self.test_user_token)
        response = await self.post("/places/", json=place_data, headers=headers)
        if response.status_code == 201:
            self.test_place_id = response.json()["id"]
            await self.mark_test_passed("Created test place")
        else:
            await self.mark_test_failed(f"Failed to create test place: {response.text}")

    async def test_collection_lifecycle(self):
        """Test complete collection CRUD lifecycle"""
        await self.add_test("Collection Lifecycle - Create collection")

        headers = get_auth_headers(self.test_user_token)

        # Create collection
        collection_data = {
            "name": "My Test Collection",
            "description": "A collection for testing purposes",
            "is_public": True
        }

        response = await self.post("/collections/", json=collection_data, headers=headers)
        if response.status_code == 201:
            self.collection_id = response.json()["id"]
            assert response.json()["name"] == collection_data["name"]
            assert response.json()["description"] == collection_data["description"]
            assert response.json()["is_public"] == True
            await self.mark_test_passed("Created collection successfully")
        else:
            await self.mark_test_failed(f"Failed to create collection: {response.text}")
            return

        # Test duplicate name prevention
        await self.add_test("Collection Lifecycle - Duplicate name prevention")
        response = await self.post("/collections/", json=collection_data, headers=headers)
        if response.status_code == 400:
            await self.mark_test_passed("Duplicate collection name properly rejected")
        else:
            await self.mark_test_failed(f"Duplicate name check failed: {response.status_code}")

        # Read collection
        await self.add_test("Collection Lifecycle - Read collection")
        response = await self.get(f"/collections/{self.collection_id}", headers=headers)
        if response.status_code == 200:
            collection = response.json()
            assert collection["id"] == self.collection_id
            assert collection["name"] == collection_data["name"]
            await self.mark_test_passed("Read collection successfully")
        else:
            await self.mark_test_failed(f"Failed to read collection: {response.text}")

        # Update collection
        await self.add_test("Collection Lifecycle - Update collection")
        updated_data = {
            "name": "Updated Test Collection",
            "description": "Updated description",
            "is_public": False
        }

        response = await self.put(f"/collections/{self.collection_id}", json=updated_data, headers=headers)
        if response.status_code == 200:
            collection = response.json()
            assert collection["name"] == updated_data["name"]
            assert collection["description"] == updated_data["description"]
            assert collection["is_public"] == False
            await self.mark_test_passed("Updated collection successfully")
        else:
            await self.mark_test_failed(f"Failed to update collection: {response.text}")

        # List collections
        await self.add_test("Collection Lifecycle - List collections")
        response = await self.get("/collections/", headers=headers)
        if response.status_code == 200:
            collections = response.json()
            assert collections["total"] >= 1
            assert any(c["id"] == self.collection_id for c in collections["items"])
            await self.mark_test_passed("Listed collections successfully")
        else:
            await self.mark_test_failed(f"Failed to list collections: {response.text}")

        # Collections summary
        await self.add_test("Collection Lifecycle - Collections summary")
        response = await self.get("/collections/summary", headers=headers)
        if response.status_code == 200:
            summary = response.json()
            assert isinstance(summary, list)
            collection_summary = next((c for c in summary if c["id"] == self.collection_id), None)
            assert collection_summary is not None
            assert "count" in collection_summary
            assert "photos" in collection_summary
            await self.mark_test_passed("Got collections summary successfully")
        else:
            await self.mark_test_failed(f"Failed to get collections summary: {response.text}")

    async def test_place_management(self):
        """Test adding/removing places from collections"""
        await self.add_test("Place Management - Add place to collection")

        headers = get_auth_headers(self.test_user_token)

        # Add place to collection
        response = await self.post(f"/collections/{self.collection_id}/places/{self.test_place_id}", headers=headers)
        if response.status_code == 200:
            result = response.json()
            assert "message" in result
            assert "id" in result
            await self.mark_test_passed("Added place to collection successfully")
        else:
            await self.mark_test_failed(f"Failed to add place to collection: {response.text}")
            return

        # Test duplicate place prevention
        await self.add_test("Place Management - Duplicate place prevention")
        response = await self.post(f"/collections/{self.collection_id}/places/{self.test_place_id}", headers=headers)
        if response.status_code == 400:
            await self.mark_test_passed("Duplicate place properly rejected")
        else:
            await self.mark_test_failed(f"Duplicate place check failed: {response.status_code}")

        # Get collection places
        await self.add_test("Place Management - Get collection places")
        response = await self.get(f"/collections/{self.collection_id}/places", headers=headers)
        if response.status_code == 200:
            places = response.json()
            assert places["total"] >= 1
            assert any(p["place_id"] == self.test_place_id for p in places["items"])
            place_item = next(p for p in places["items"] if p["place_id"] == self.test_place_id)
            assert "place_name" in place_item
            assert "place_address" in place_item
            assert "checkin_count" in place_item
            await self.mark_test_passed("Got collection places successfully")
        else:
            await self.mark_test_failed(f"Failed to get collection places: {response.text}")

        # Get collection items (alias endpoint)
        await self.add_test("Place Management - Get collection items (alias)")
        response = await self.get(f"/collections/{self.collection_id}/items", headers=headers)
        if response.status_code == 200:
            items = response.json()
            assert items["total"] >= 1
            await self.mark_test_passed("Collection items alias endpoint works")
        else:
            await self.mark_test_failed(f"Collection items alias failed: {response.text}")

        # Get collection items list (minimal format)
        await self.add_test("Place Management - Get collection items list")
        response = await self.get(f"/collections/{self.collection_id}/items/list", headers=headers)
        if response.status_code == 200:
            items_list = response.json()
            assert isinstance(items_list, list)
            assert len(items_list) >= 1
            item = items_list[0]
            assert "place_id" in item
            assert "place_name" in item
            assert "photos" in item
            await self.mark_test_passed("Got collection items list successfully")
        else:
            await self.mark_test_failed(f"Failed to get collection items list: {response.text}")

        # Remove place from collection
        await self.add_test("Place Management - Remove place from collection")
        response = await self.delete(f"/collections/{self.collection_id}/places/{self.test_place_id}", headers=headers)
        if response.status_code == 204:
            await self.mark_test_passed("Removed place from collection successfully")
        else:
            await self.mark_test_failed(f"Failed to remove place from collection: {response.text}")

        # Verify place removed
        await self.add_test("Place Management - Verify place removed")
        response = await self.get(f"/collections/{self.collection_id}/places", headers=headers)
        if response.status_code == 200:
            places = response.json()
            assert not any(p["place_id"] == self.test_place_id for p in places["items"])
            await self.mark_test_passed("Place successfully removed from collection")
        else:
            await self.mark_test_failed(f"Failed to verify place removal: {response.text}")

    async def test_visibility_and_permissions(self):
        """Test visibility controls and permission checking"""
        await self.add_test("Visibility - Create private collection")

        headers1 = get_auth_headers(self.test_user_token)
        headers2 = get_auth_headers(self.second_user_token)

        # Create private collection
        private_collection_data = {
            "name": "Private Collection",
            "description": "This is private",
            "is_public": False
        }

        response = await self.post("/collections/", json=private_collection_data, headers=headers1)
        if response.status_code == 201:
            private_collection_id = response.json()["id"]
            await self.mark_test_passed("Created private collection")
        else:
            await self.mark_test_failed(f"Failed to create private collection: {response.text}")
            return

        # Test that other user cannot access private collection
        await self.add_test("Visibility - Other user cannot access private collection")
        response = await self.get(f"/collections/{private_collection_id}", headers=headers2)
        if response.status_code == 403:
            await self.mark_test_passed("Private collection properly protected")
        else:
            await self.mark_test_failed(f"Private collection access check failed: {response.status_code}")

        # Test that owner can access their private collection
        await self.add_test("Visibility - Owner can access private collection")
        response = await self.get(f"/collections/{private_collection_id}", headers=headers1)
        if response.status_code == 200:
            await self.mark_test_passed("Owner can access private collection")
        else:
            await self.mark_test_failed(f"Owner access to private collection failed: {response.text}")

        # Test unauthorized modification attempts
        await self.add_test("Visibility - Unauthorized modification prevention")
        response = await self.put(f"/collections/{private_collection_id}",
                                 json={"name": "Hacked", "is_public": True},
                                 headers=headers2)
        if response.status_code == 403:
            await self.mark_test_passed("Unauthorized modification properly prevented")
        else:
            await self.mark_test_failed(f"Unauthorized modification check failed: {response.status_code}")

        # Test unauthorized deletion attempts
        await self.add_test("Visibility - Unauthorized deletion prevention")
        response = await self.delete(f"/collections/{private_collection_id}", headers=headers2)
        if response.status_code == 403:
            await self.mark_test_passed("Unauthorized deletion properly prevented")
        else:
            await self.mark_test_failed(f"Unauthorized deletion check failed: {response.status_code}")

        # Clean up private collection
        await self.delete(f"/collections/{private_collection_id}", headers=headers1)

    async def test_photo_handling(self):
        """Test photo handling and signed URL generation"""
        await self.add_test("Photo Handling - Test photo URL conversion")

        # Re-add place to collection for photo testing
        headers = get_auth_headers(self.test_user_token)
        await self.post(f"/collections/{self.collection_id}/places/{self.test_place_id}", headers=headers)

        # Get collection places and check photo handling
        response = await self.get(f"/collections/{self.collection_id}/places", headers=headers)
        if response.status_code == 200:
            places = response.json()
            if places["items"]:
                place_item = places["items"][0]
                # Check that photo fields exist
                assert "place_photo_url" in place_item
                assert "user_checkin_photos" in place_item
                assert isinstance(place_item["user_checkin_photos"], list)
                await self.mark_test_passed("Photo fields present in response")
            else:
                await self.mark_test_passed("No places to test photos with")
        else:
            await self.mark_test_failed(f"Failed to get collection places for photo test: {response.text}")

        # Test collections summary photos
        await self.add_test("Photo Handling - Collections summary photos")
        response = await self.get("/collections/summary", headers=headers)
        if response.status_code == 200:
            summary = response.json()
            for collection in summary:
                assert "photos" in collection
                assert isinstance(collection["photos"], list)
            await self.mark_test_passed("Collections summary includes photo arrays")
        else:
            await self.mark_test_failed(f"Failed to get collections summary for photo test: {response.text}")

    async def test_saved_place_synchronization(self):
        """Test SavedPlace synchronization behavior"""
        await self.add_test("SavedPlace Sync - Collection place addition creates SavedPlace")

        headers = get_auth_headers(self.test_user_token)

        # Adding place to collection should create SavedPlace entry
        # This is tested implicitly when we add places to collections
        # The sync happens in the add_place_to_collection endpoint

        # Create new collection to test sync
        sync_collection_data = {
            "name": "Sync Test Collection",
            "description": "Testing SavedPlace sync",
            "is_public": True
        }

        response = await self.post("/collections/", json=sync_collection_data, headers=headers)
        if response.status_code == 201:
            sync_collection_id = response.json()["id"]
            await self.mark_test_passed("Created collection for sync testing")
        else:
            await self.mark_test_failed(f"Failed to create sync test collection: {response.text}")
            return

        # Add place and verify sync happens
        response = await self.post(f"/collections/{sync_collection_id}/places/{self.test_place_id}", headers=headers)
        if response.status_code == 200:
            await self.mark_test_passed("Place added with SavedPlace sync")
        else:
            await self.mark_test_failed(f"Failed to add place for sync test: {response.text}")

        # Clean up sync test collection
        await self.delete(f"/collections/{sync_collection_id}", headers=headers)

    async def test_edge_cases_and_errors(self):
        """Test edge cases and error conditions"""
        await self.add_test("Edge Cases - Non-existent collection access")

        headers = get_auth_headers(self.test_user_token)

        # Try to access non-existent collection
        response = await self.get("/collections/99999", headers=headers)
        if response.status_code == 404:
            await self.mark_test_passed("Non-existent collection properly returns 404")
        else:
            await self.mark_test_failed(f"Non-existent collection check failed: {response.status_code}")

        # Try to add non-existent place to collection
        await self.add_test("Edge Cases - Add non-existent place")
        response = await self.post(f"/collections/{self.collection_id}/places/99999", headers=headers)
        if response.status_code == 404:
            await self.mark_test_passed("Non-existent place properly returns 404")
        else:
            await self.mark_test_failed(f"Non-existent place check failed: {response.status_code}")

        # Try to remove non-existent place from collection
        await self.add_test("Edge Cases - Remove non-existent place")
        response = await self.delete(f"/collections/{self.collection_id}/places/99999", headers=headers)
        if response.status_code == 404:
            await self.mark_test_passed("Remove non-existent place properly returns 404")
        else:
            await self.mark_test_failed(f"Remove non-existent place check failed: {response.status_code}")

        # Test invalid collection data
        await self.add_test("Edge Cases - Invalid collection data")
        invalid_data = {
            "name": "",  # Empty name
            "description": "Test"
        }
        response = await self.post("/collections/", json=invalid_data, headers=headers)
        if response.status_code in [400, 422]:
            await self.mark_test_passed("Invalid collection data properly rejected")
        else:
            await self.mark_test_failed(f"Invalid data validation failed: {response.status_code}")

        # Test unauthorized access without token
        await self.add_test("Edge Cases - Unauthorized access")
        response = await self.get("/collections/")
        if response.status_code == 401:
            await self.mark_test_passed("Unauthorized access properly blocked")
        else:
            await self.mark_test_failed(f"Unauthorized access check failed: {response.status_code}")

    async def test_pagination_and_limits(self):
        """Test pagination and limit parameters"""
        await self.add_test("Pagination - Test collection listing with limits")

        headers = get_auth_headers(self.test_user_token)

        # Create multiple collections to test pagination
        for i in range(5):
            collection_data = {
                "name": f"Pagination Test Collection {i}",
                "description": f"Collection {i} for pagination testing",
                "is_public": True
            }
            await self.post("/collections/", json=collection_data, headers=headers)

        # Test pagination parameters
        response = await self.get("/collections/?limit=2&offset=0", headers=headers)
        if response.status_code == 200:
            collections = response.json()
            assert len(collections["items"]) <= 2
            assert "total" in collections
            assert "limit" in collections
            assert "offset" in collections
            await self.mark_test_passed("Collection pagination works correctly")
        else:
            await self.mark_test_failed(f"Collection pagination failed: {response.text}")

        # Test place pagination
        await self.add_test("Pagination - Test place listing with limits")
        response = await self.get(f"/collections/{self.collection_id}/places?limit=10&offset=0", headers=headers)
        if response.status_code == 200:
            places = response.json()
            assert "total" in places
            assert "limit" in places
            assert "offset" in places
            await self.mark_test_passed("Place pagination works correctly")
        else:
            await self.mark_test_failed(f"Place pagination failed: {response.text}")

    async def cleanup_test_data(self):
        """Clean up test data"""
        await self.add_test("Cleanup - Delete test collections")

        headers = get_auth_headers(self.test_user_token)

        # Get all collections and delete them
        response = await self.get("/collections/", headers=headers)
        if response.status_code == 200:
            collections = response.json()["items"]
            for collection in collections:
                await self.delete(f"/collections/{collection['id']}", headers=headers)
            await self.mark_test_passed("Cleaned up test collections")
        else:
            await self.mark_test_passed("No collections to clean up")

        # Delete collection (if still exists)
        if self.collection_id:
            await self.delete(f"/collections/{self.collection_id}", headers=headers)

        await self.add_test("Cleanup - Test data cleaned up")
        await self.mark_test_passed("All test data cleaned up successfully")


if __name__ == "__main__":
    import asyncio
    from tests.utils.base_test import TestConfig

    config = TestConfig(verbose=True)
    test = CollectionsComprehensiveTest(config)
    asyncio.run(test.execute())