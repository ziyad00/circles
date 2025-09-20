"""
End-to-end test for complete user workflow
"""
import asyncio
from typing import Dict, Any, Optional

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse
from ..utils.test_helpers import TestDataFactory, TestAssertions, TestFixtures


class UserWorkflowTest(BaseTest):
    """Test complete user workflow from registration to interaction"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)
        self.created_place_id: Optional[int] = None
        self.created_collection_id: Optional[int] = None
        self.dm_thread_id: Optional[int] = None
        self.other_user_id: Optional[int] = None

    async def _setup_test_data(self):
        """Setup test data for workflow"""
        await super()._setup_test_data()

        # Create another test user for interaction testing
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            from app.models import User
            from sqlalchemy import select

            # Check if other test user exists
            result = await db.execute(select(User).where(User.phone == "+1234567891"))
            other_user = result.scalar_one_or_none()

            if not other_user:
                other_user = User(
                    phone="+1234567891",
                    username="testuser2",
                    name="Test User 2",
                    is_verified=True
                )
                db.add(other_user)
                await db.commit()
                await db.refresh(other_user)

            self.other_user_id = other_user.id

    async def teardown(self):
        """Cleanup after tests"""
        await self.client.close()
        await super().teardown()

    async def test_complete_user_workflow(self) -> Optional[Dict[str, Any]]:
        """Test complete user workflow"""
        workflow_results = {}

        # Step 1: Health check
        health_response = APIResponse(await self.client.get("/health"))
        if health_response.is_success():
            workflow_results["health"] = "OK"
        else:
            return None

        # Step 2: Explore places
        nearby_response = APIResponse(await self.client.get(
            "/places/nearby",
            params={"lat": 40.7128, "lng": -74.0060,
                    "radius_m": 1000, "limit": 5}
        ))
        if nearby_response.is_success():
            workflow_results["nearby_places"] = nearby_response.json.get(
                "total", 0)

        # Step 3: Create a place
        place_data = TestFixtures.get_sample_place_data()
        place_response = APIResponse(await self.client.post(
            "/places/",
            json_data=place_data,
            headers=self.get_headers()
        ))
        if place_response.is_success():
            self.created_place_id = place_response.json.get("id")
            workflow_results["created_place"] = self.created_place_id

        # Step 4: Create a collection
        collection_data = TestFixtures.get_sample_collection_data()
        collection_response = APIResponse(await self.client.post(
            "/collections/",
            json_data=collection_data,
            headers=self.get_headers()
        ))
        if collection_response.is_success():
            self.created_collection_id = collection_response.json.get("id")
            workflow_results["created_collection"] = self.created_collection_id

        # Step 5: Add place to collection
        if self.created_place_id and self.created_collection_id:
            add_place_response = APIResponse(await self.client.post(
                f"/collections/{self.created_collection_id}/places/{self.created_place_id}",
                headers=self.get_headers()
            ))
            if add_place_response.is_success():
                workflow_results["added_place_to_collection"] = True

        # Step 6: Start a DM conversation
        if self.other_user_id:
            dm_response = APIResponse(await self.client.post(
                "/dms/open",
                json_data={"other_user_id": self.other_user_id},
                headers=self.get_headers()
            ))
            if dm_response.is_success():
                self.dm_thread_id = dm_response.json.get("id")
                workflow_results["dm_thread"] = self.dm_thread_id

        # Step 7: Send a message
        if self.dm_thread_id:
            message_response = APIResponse(await self.client.post(
                f"/dms/{self.dm_thread_id}/messages",
                json_data={"text": "Hello from the workflow test!",
                           "message_type": "text"},
                headers=self.get_headers()
            ))
            if message_response.is_success():
                workflow_results["sent_message"] = message_response.json.get(
                    "id")

        # Step 8: Check collections summary
        summary_response = APIResponse(await self.client.get(
            "/collections/summary",
            headers=self.get_headers()
        ))
        if summary_response.is_success():
            workflow_results["collections_summary"] = summary_response.json

        # Step 9: Get trending places
        trending_response = APIResponse(await self.client.get(
            "/places/trending",
            params={"lat": 40.7128, "lng": -74.0060,
                    "time_window": "24h", "limit": 5}
        ))
        if trending_response.is_success():
            workflow_results["trending_places"] = trending_response.json.get(
                "total", 0)

        return workflow_results

    async def test_place_discovery_workflow(self) -> Optional[Dict[str, Any]]:
        """Test place discovery workflow"""
        discovery_results = {}

        # Step 1: Search for places
        search_response = APIResponse(await self.client.post(
            "/places/search/advanced",
            json_data={
                "query": "coffee",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "radius_km": 5,
                "limit": 10
            },
            headers=self.get_headers()
        ))
        if search_response.is_success():
            discovery_results["search_results"] = search_response.json.get(
                "total", 0)

        # Step 2: Get recommendations
        recommendations_response = APIResponse(await self.client.get(
            "/places/recommendations",
            params={"lat": 40.7128, "lng": -74.0060, "limit": 5},
            headers=self.get_headers()
        ))
        if recommendations_response.is_success():
            discovery_results["recommendations"] = recommendations_response.json.get(
                "total", 0)

        # Step 3: Get global trending
        global_trending_response = APIResponse(await self.client.get(
            "/places/trending/global",
            params={"lat": 40.7128, "lng": -74.0060, "limit": 5}
        ))
        if global_trending_response.is_success():
            discovery_results["global_trending"] = global_trending_response.json.get(
                "total", 0)

        return discovery_results

    async def test_social_interaction_workflow(self) -> Optional[Dict[str, Any]]:
        """Test social interaction workflow"""
        social_results = {}

        # Step 1: Get DM threads
        threads_response = APIResponse(await self.client.get(
            "/dms/",
            headers=self.get_headers()
        ))
        if threads_response.is_success():
            social_results["dm_threads"] = threads_response.json.get(
                "total", 0)

        # Step 2: Get unread count
        unread_response = APIResponse(await self.client.get(
            "/dms/unread-count",
            headers=self.get_headers()
        ))
        if unread_response.is_success():
            social_results["unread_count"] = unread_response.json.get(
                "unread", 0)

        # Step 3: Send DM request
        if self.other_user_id:
            request_response = APIResponse(await self.client.post(
                "/dms/requests",
                json_data={
                    "recipient_id": self.other_user_id,
                    "text": "Hello! I'd like to connect with you."
                },
                headers=self.get_headers()
            ))
            if request_response.is_success():
                social_results["dm_request"] = request_response.json.get("id")

        return social_results

    async def run_tests(self):
        """Run all workflow tests"""
        self._log("🔄 Testing Complete User Workflows...")

        # Test 1: Complete user workflow
        await self.run_test("Complete User Workflow", self.test_complete_user_workflow)

        # Test 2: Place discovery workflow
        await self.run_test("Place Discovery Workflow", self.test_place_discovery_workflow)

        # Test 3: Social interaction workflow
        await self.run_test("Social Interaction Workflow", self.test_social_interaction_workflow)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = UserWorkflowTest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
