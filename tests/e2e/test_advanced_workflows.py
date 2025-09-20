"""
End-to-End tests for Advanced User Workflows
"""
import asyncio
from typing import Dict, Any, Optional

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse
from ..utils.test_helpers import TestAssertions, TestDataFactory, TestCleanup, TestFixtures


class AdvancedWorkflowsTest(BaseTest):
    """Test advanced user workflows and complex scenarios"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)
        self.test_place_id: int = 0
        self.test_collection_id: int = 0
        self.test_checkin_id: int = 0

    async def teardown(self):
        """Cleanup after tests"""
        await self.client.close()
        await super().teardown()

    async def test_complete_place_discovery_workflow(self) -> Optional[Dict[str, Any]]:
        """Test complete place discovery workflow"""
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

        # Step 2: Get nearby places
        nearby_response = APIResponse(await self.client.get(
            "/places/nearby?lat=40.7128&lng=-74.0060&radius_m=1000&limit=10",
            headers=self.get_headers()
        ))

        # Step 3: Get trending places
        trending_response = APIResponse(await self.client.get(
            "/places/trending?lat=40.7128&lng=-74.0060&time_window=24h&limit=10",
            headers=self.get_headers()
        ))

        # Step 4: Get recommendations
        recommendations_response = APIResponse(await self.client.get(
            "/places/recommendations?lat=40.7128&lng=-74.0060&limit=10",
            headers=self.get_headers()
        ))

        # All should succeed
        if all(r.is_success() for r in [search_response, nearby_response, trending_response, recommendations_response]):
            return {
                "search_results": len(search_response.json.get("items", [])),
                "nearby_results": len(nearby_response.json.get("items", [])),
                "trending_results": len(trending_response.json.get("items", [])),
                "recommendations_results": len(recommendations_response.json.get("items", []))
            }

        return None

    async def test_complete_collection_management_workflow(self) -> Optional[Dict[str, Any]]:
        """Test complete collection management workflow"""
        # Step 1: Create a collection
        create_response = APIResponse(await self.client.post(
            "/collections/",
            json_data={
                "name": "Advanced Test Collection",
                "description": "A collection for advanced testing",
                "is_public": True
            },
            headers=self.get_headers()
        ))

        if create_response.is_success():
            self.test_collection_id = create_response.json.get("id")

            # Step 2: Create a place
            place_response = APIResponse(await self.client.post(
                "/places/",
                json_data=TestFixtures.get_sample_place_data(0),
                headers=self.get_headers()
            ))

            if place_response.is_success():
                self.test_place_id = place_response.json.get("id")

                # Step 3: Add place to collection
                add_response = APIResponse(await self.client.post(
                    f"/collections/{self.test_collection_id}/places/{self.test_place_id}",
                    headers=self.get_headers()
                ))

                # Step 4: Get collection with places
                get_response = APIResponse(await self.client.get(
                    f"/collections/{self.test_collection_id}/places",
                    headers=self.get_headers()
                ))

                # Step 5: Update collection
                update_response = APIResponse(await self.client.patch(
                    f"/collections/{self.test_collection_id}",
                    json_data={
                        "name": "Updated Advanced Test Collection",
                        "description": "Updated description"
                    },
                    headers=self.get_headers()
                ))

                # Step 6: Get collection summary
                summary_response = APIResponse(await self.client.get(
                    "/collections/summary",
                    headers=self.get_headers()
                ))

                if all(r.is_success() for r in [add_response, get_response, update_response, summary_response]):
                    return {
                        "collection_created": True,
                        "place_added": True,
                        "collection_updated": True,
                        "summary_retrieved": True
                    }

        return None

    async def test_complete_checkin_workflow(self) -> Optional[Dict[str, Any]]:
        """Test complete check-in workflow"""
        if self.test_place_id:
            # Step 1: Create a check-in
            checkin_response = APIResponse(await self.client.post(
                "/checkins/",
                json_data={
                    "place_id": self.test_place_id,
                    "text": "Amazing place! Great atmosphere and coffee.",
                    "visibility": "public"
                },
                headers=self.get_headers()
            ))

            if checkin_response.is_success():
                self.test_checkin_id = checkin_response.json.get("id")

                # Step 2: Get the check-in
                get_response = APIResponse(await self.client.get(
                    f"/checkins/{self.test_checkin_id}",
                    headers=self.get_headers()
                ))

                # Step 3: Update the check-in
                update_response = APIResponse(await self.client.patch(
                    f"/checkins/{self.test_checkin_id}",
                    json_data={
                        "text": "Updated: Even better than I thought!",
                        "visibility": "private"
                    },
                    headers=self.get_headers()
                ))

                # Step 4: Get place check-ins
                place_checkins_response = APIResponse(await self.client.get(
                    f"/places/{self.test_place_id}/checkins",
                    headers=self.get_headers()
                ))

                # Step 5: Get user check-ins
                user_checkins_response = APIResponse(await self.client.get(
                    "/checkins/",
                    headers=self.get_headers()
                ))

                if all(r.is_success() for r in [get_response, update_response, place_checkins_response, user_checkins_response]):
                    return {
                        "checkin_created": True,
                        "checkin_retrieved": True,
                        "checkin_updated": True,
                        "place_checkins_retrieved": True,
                        "user_checkins_retrieved": True
                    }

        return None

    async def test_complete_social_workflow(self) -> Optional[Dict[str, Any]]:
        """Test complete social interaction workflow"""
        # Step 1: Get user profile
        profile_response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}",
            headers=self.get_headers()
        ))

        # Step 2: Update user profile
        update_response = APIResponse(await self.client.patch(
            f"/users/{self.test_user.id}",
            json_data={
                "name": "Social Test User",
                "bio": "Testing social features",
                "availability_status": "available"
            },
            headers=self.get_headers()
        ))

        # Step 3: Get user stats
        stats_response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/stats",
            headers=self.get_headers()
        ))

        # Step 4: Get user collections
        collections_response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/collections",
            headers=self.get_headers()
        ))

        # Step 5: Get user check-ins
        checkins_response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/checkins",
            headers=self.get_headers()
        ))

        if all(r.is_success() for r in [profile_response, update_response, stats_response, collections_response, checkins_response]):
            return {
                "profile_retrieved": True,
                "profile_updated": True,
                "stats_retrieved": True,
                "collections_retrieved": True,
                "checkins_retrieved": True
            }

        return None

    async def test_complete_dm_workflow(self) -> Optional[Dict[str, Any]]:
        """Test complete direct messaging workflow"""
        # Step 1: Get DM unread count
        unread_response = APIResponse(await self.client.get(
            "/dms/unread-count",
            headers=self.get_headers()
        ))

        # Step 2: Get DM requests
        requests_response = APIResponse(await self.client.get(
            "/dms/requests",
            headers=self.get_headers()
        ))

        # Step 3: Get DM threads
        threads_response = APIResponse(await self.client.get(
            "/dms/threads",
            headers=self.get_headers()
        ))

        # Step 4: Send DM request (to self for testing)
        request_response = APIResponse(await self.client.post(
            "/dms/request",
            json_data={"other_user_id": self.test_user.id},
            headers=self.get_headers()
        ))

        # Step 5: Open DM thread
        open_response = APIResponse(await self.client.post(
            "/dms/open",
            json_data={"other_user_id": self.test_user.id},
            headers=self.get_headers()
        ))

        if all(r.is_success() for r in [unread_response, requests_response, threads_response, request_response, open_response]):
            return {
                "unread_count_retrieved": True,
                "requests_retrieved": True,
                "threads_retrieved": True,
                "request_sent": True,
                "thread_opened": True
            }

        return None

    async def test_complete_privacy_workflow(self) -> Optional[Dict[str, Any]]:
        """Test complete privacy settings workflow"""
        # Step 1: Update privacy settings
        privacy_response = APIResponse(await self.client.patch(
            f"/users/{self.test_user.id}/privacy",
            json_data={
                "profile_visibility": "private",
                "dm_privacy": "followers",
                "checkins_default_visibility": "private",
                "collections_default_visibility": "private"
            },
            headers=self.get_headers()
        ))

        # Step 2: Update availability settings
        availability_response = APIResponse(await self.client.patch(
            f"/users/{self.test_user.id}/availability",
            json_data={
                "availability_status": "available",
                "availability_mode": "manual"
            },
            headers=self.get_headers()
        ))

        # Step 3: Get updated profile
        profile_response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}",
            headers=self.get_headers()
        ))

        if all(r.is_success() for r in [privacy_response, availability_response, profile_response]):
            return {
                "privacy_updated": True,
                "availability_updated": True,
                "profile_retrieved": True
            }

        return None

    async def test_complete_search_workflow(self) -> Optional[Dict[str, Any]]:
        """Test complete search functionality workflow"""
        # Step 1: Search places
        places_search_response = APIResponse(await self.client.post(
            "/places/search/advanced",
            json_data={
                "query": "restaurant",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "radius_km": 10,
                "limit": 20
            },
            headers=self.get_headers()
        ))

        # Step 2: Search users
        users_search_response = APIResponse(await self.client.get(
            "/users/search?q=test",
            headers=self.get_headers()
        ))

        # Step 3: Get global trending
        global_trending_response = APIResponse(await self.client.get(
            "/places/trending/global?limit=20",
            headers=self.get_headers()
        ))

        # Step 4: Get recommendations
        recommendations_response = APIResponse(await self.client.get(
            "/places/recommendations?lat=40.7128&lng=-74.0060&limit=20",
            headers=self.get_headers()
        ))

        if all(r.is_success() for r in [places_search_response, users_search_response, global_trending_response, recommendations_response]):
            return {
                "places_search_results": len(places_search_response.json.get("items", [])),
                "users_search_results": len(users_search_response.json.get("items", [])),
                "global_trending_results": len(global_trending_response.json.get("items", [])),
                "recommendations_results": len(recommendations_response.json.get("items", []))
            }

        return None

    async def test_complete_analytics_workflow(self) -> Optional[Dict[str, Any]]:
        """Test complete analytics and reporting workflow"""
        # Step 1: Get user stats
        user_stats_response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/stats",
            headers=self.get_headers()
        ))

        # Step 2: Get collections summary
        collections_summary_response = APIResponse(await self.client.get(
            "/collections/summary",
            headers=self.get_headers()
        ))

        # Step 3: Get user check-ins
        user_checkins_response = APIResponse(await self.client.get(
            "/checkins/",
            headers=self.get_headers()
        ))

        # Step 4: Get user collections
        user_collections_response = APIResponse(await self.client.get(
            "/collections/",
            headers=self.get_headers()
        ))

        if all(r.is_success() for r in [user_stats_response, collections_summary_response, user_checkins_response, user_collections_response]):
            return {
                "user_stats_retrieved": True,
                "collections_summary_retrieved": True,
                "user_checkins_retrieved": True,
                "user_collections_retrieved": True
            }

        return None

    async def run_tests(self):
        """Run all advanced workflow tests"""
        self._log("🚀 Testing Advanced User Workflows...")

        # Core workflow tests
        await self.run_test("Complete Place Discovery Workflow", self.test_complete_place_discovery_workflow)
        await self.run_test("Complete Collection Management Workflow", self.test_complete_collection_management_workflow)
        await self.run_test("Complete Check-in Workflow", self.test_complete_checkin_workflow)
        await self.run_test("Complete Social Workflow", self.test_complete_social_workflow)
        await self.run_test("Complete DM Workflow", self.test_complete_dm_workflow)
        await self.run_test("Complete Privacy Workflow", self.test_complete_privacy_workflow)
        await self.run_test("Complete Search Workflow", self.test_complete_search_workflow)
        await self.run_test("Complete Analytics Workflow", self.test_complete_analytics_workflow)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = AdvancedWorkflowsTest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
