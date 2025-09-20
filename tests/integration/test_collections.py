"""
Integration tests for Collections API
"""
import asyncio
from typing import Dict, Any, Optional

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse
from ..utils.test_helpers import TestDataFactory, TestAssertions, TestFixtures


class CollectionsAPITest(BaseTest):
    """Test collections API endpoints"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)
        self.test_collection_id: Optional[int] = None

    async def teardown(self):
        """Cleanup after tests"""
        await self.client.close()
        await super().teardown()

    async def test_health_check(self) -> Optional[Dict[str, Any]]:
        """Test health endpoint"""
        response = APIResponse(await self.client.get("/health"))
        if response.is_success():
            return response.json
        return None

    async def test_collections_summary(self) -> Optional[Dict[str, Any]]:
        """Test collections summary endpoint"""
        response = APIResponse(await self.client.get("/collections/summary", headers=self.get_headers()))
        if response.is_success():
            return response.json
        return None

    async def test_collections_list(self) -> Optional[Dict[str, Any]]:
        """Test collections list endpoint"""
        response = APIResponse(await self.client.get("/collections/", headers=self.get_headers()))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_create_collection(self) -> Optional[Dict[str, Any]]:
        """Test create collection endpoint"""
        collection_data = TestFixtures.get_sample_collection_data()
        response = APIResponse(await self.client.post(
            "/collections/",
            json_data=collection_data,
            headers=self.get_headers()
        ))
        if response.is_success():
            data = response.json
            self.test_collection_id = data.get("id")
            TestAssertions.assert_json_structure(
                response, ["id", "name", "user_id", "created_at"])
            return data
        return None

    async def test_get_collection(self) -> Optional[Dict[str, Any]]:
        """Test get specific collection endpoint"""
        if not self.test_collection_id:
            return None

        response = APIResponse(await self.client.get(
            f"/collections/{self.test_collection_id}",
            headers=self.get_headers()
        ))
        if response.is_success():
            TestAssertions.assert_json_structure(
                response, ["id", "name", "user_id", "created_at"])
            return response.json
        return None

    async def test_update_collection(self) -> Optional[Dict[str, Any]]:
        """Test update collection endpoint"""
        if not self.test_collection_id:
            return None

        update_data = {
            "name": "Updated Test Collection",
            "description": "Updated description"
        }
        response = APIResponse(await self.client.put(
            f"/collections/{self.test_collection_id}",
            json_data=update_data,
            headers=self.get_headers()
        ))
        if response.is_success():
            data = response.json
            TestAssertions.assert_json_contains(
                response, "name", "Updated Test Collection")
            return data
        return None

    async def test_get_collection_places(self) -> Optional[Dict[str, Any]]:
        """Test get collection places endpoint"""
        if not self.test_collection_id:
            return None

        response = APIResponse(await self.client.get(
            f"/collections/{self.test_collection_id}/places",
            headers=self.get_headers()
        ))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_get_collection_items_list(self) -> Optional[Dict[str, Any]]:
        """Test get collection items list endpoint"""
        if not self.test_collection_id:
            return None

        response = APIResponse(await self.client.get(
            f"/collections/{self.test_collection_id}/items/list",
            headers=self.get_headers()
        ))
        if response.is_success():
            data = response.json
            assert isinstance(data, list), "Items list should be a list"
            return data
        return None

    async def test_add_place_to_collection(self) -> Optional[Dict[str, Any]]:
        """Test add place to collection endpoint"""
        if not self.test_collection_id:
            return None

        # First create a test place
        test_places = await TestDataFactory.create_test_places(1)
        if not test_places:
            return None

        place_id = test_places[0].id

        response = APIResponse(await self.client.post(
            f"/collections/{self.test_collection_id}/places/{place_id}",
            headers=self.get_headers()
        ))
        if response.is_success():
            return response.json
        return None

    async def test_remove_place_from_collection(self) -> Optional[Dict[str, Any]]:
        """Test remove place from collection endpoint"""
        if not self.test_collection_id:
            return None

        # Get a place from the collection first
        places_response = APIResponse(await self.client.get(
            f"/collections/{self.test_collection_id}/places",
            headers=self.get_headers()
        ))

        if places_response.is_success():
            places_data = places_response.json
            if places_data.get("items"):
                place_id = places_data["items"][0]["place_id"]

                response = APIResponse(await self.client.delete(
                    f"/collections/{self.test_collection_id}/places/{place_id}",
                    headers=self.get_headers()
                ))
                if response.status_code == 204:
                    return {"deleted": True}
        return None

    async def test_delete_collection(self) -> Optional[Dict[str, Any]]:
        """Test delete collection endpoint"""
        if not self.test_collection_id:
            return None

        response = APIResponse(await self.client.delete(
            f"/collections/{self.test_collection_id}",
            headers=self.get_headers()
        ))
        if response.status_code == 204:
            return {"deleted": True}
        return None

    async def test_collections_without_auth(self) -> Optional[Dict[str, Any]]:
        """Test collections endpoints without authentication (should fail)"""
        response = APIResponse(await self.client.get("/collections/summary"))
        if response.status_code == 401:
            return {"unauthorized": True}
        return None

    async def run_tests(self):
        """Run all collections tests"""
        self._log("🧪 Testing Collections API Endpoints...")

        # Test 1: Health check
        await self.run_test("Health Check", self.test_health_check)

        # Test 2: Collections without auth (should fail)
        await self.run_test("Collections Without Auth", self.test_collections_without_auth)

        # Test 3: Collections summary
        await self.run_test("Collections Summary", self.test_collections_summary)

        # Test 4: Collections list
        await self.run_test("Collections List", self.test_collections_list)

        # Test 5: Create collection
        await self.run_test("Create Collection", self.test_create_collection)

        if self.test_collection_id:
            # Test 6: Get collection
            await self.run_test("Get Collection", self.test_get_collection)

            # Test 7: Update collection
            await self.run_test("Update Collection", self.test_update_collection)

            # Test 8: Get collection places (empty)
            await self.run_test("Get Collection Places (Empty)", self.test_get_collection_places)

            # Test 9: Get collection items list (empty)
            await self.run_test("Get Collection Items List (Empty)", self.test_get_collection_items_list)

            # Test 10: Add place to collection
            await self.run_test("Add Place to Collection", self.test_add_place_to_collection)

            # Test 11: Get collection places (with data)
            await self.run_test("Get Collection Places (With Data)", self.test_get_collection_places)

            # Test 12: Remove place from collection
            await self.run_test("Remove Place from Collection", self.test_remove_place_from_collection)

            # Test 13: Delete collection
            await self.run_test("Delete Collection", self.test_delete_collection)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = CollectionsAPITest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
