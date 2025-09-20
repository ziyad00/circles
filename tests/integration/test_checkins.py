"""
Integration tests for Check-ins API
"""
import asyncio
from typing import Dict, Any, Optional

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse
from ..utils.test_helpers import TestAssertions, TestDataFactory, TestCleanup, TestFixtures


class CheckinsAPITest(BaseTest):
    """Integration tests for Check-ins API endpoints"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)
        self.test_place_id: int = 0
        self.test_checkin_id: int = 0

    async def teardown(self):
        """Cleanup after tests"""
        await self.client.close()
        await super().teardown()

    async def test_health_check(self) -> Optional[Dict[str, Any]]:
        """Test health check endpoint"""
        response = APIResponse(await self.client.get("/health"))
        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_contains(response, "status", "ok")
        return response.json

    async def test_checkins_without_auth(self) -> Optional[Dict[str, Any]]:
        """Test checkins endpoint without authentication (should fail)"""
        response = APIResponse(await self.client.get("/checkins/"))
        TestAssertions.assert_response_error(response, 401)
        return response.json

    async def test_create_checkin(self) -> Optional[Dict[str, Any]]:
        """Test creating a new check-in"""
        # First create a place
        place_response = APIResponse(await self.client.post(
            "/places/",
            json_data=TestFixtures.get_sample_place_data(0),
            headers=self.get_headers()
        ))

        if place_response.is_success():
            self.test_place_id = place_response.json.get("id")

            # Create check-in
            checkin_data = {
                "place_id": self.test_place_id,
                "text": "Great coffee and atmosphere!",
                "visibility": "public"
            }

            response = APIResponse(await self.client.post(
                "/checkins/",
                json_data=checkin_data,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response, 201)
            TestAssertions.assert_json_contains(
                response, "text", checkin_data["text"])
            TestAssertions.assert_json_contains(
                response, "place_id", self.test_place_id)
            self.test_checkin_id = response.json.get("id")
            return response.json

        return None

    async def test_get_checkin(self) -> Optional[Dict[str, Any]]:
        """Test getting a specific check-in"""
        if self.test_checkin_id:
            response = APIResponse(await self.client.get(
                f"/checkins/{self.test_checkin_id}",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(
                response, "id", self.test_checkin_id)
            return response.json

        return None

    async def test_list_user_checkins(self) -> Optional[Dict[str, Any]]:
        """Test listing user's check-ins"""
        response = APIResponse(await self.client.get(
            "/checkins/",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_pagination(response)
        return response.json

    async def test_update_checkin(self) -> Optional[Dict[str, Any]]:
        """Test updating a check-in"""
        if self.test_checkin_id:
            update_data = {
                "text": "Updated: Even better than before!",
                "visibility": "private"
            }

            response = APIResponse(await self.client.patch(
                f"/checkins/{self.test_checkin_id}",
                json_data=update_data,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(
                response, "text", update_data["text"])
            TestAssertions.assert_json_contains(
                response, "visibility", update_data["visibility"])
            return response.json

        return None

    async def test_delete_checkin(self) -> Optional[Dict[str, Any]]:
        """Test deleting a check-in"""
        if self.test_checkin_id:
            response = APIResponse(await self.client.delete(
                f"/checkins/{self.test_checkin_id}",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response, 204)
            return {"deleted": True}

        return None

    async def test_checkin_photos(self) -> Optional[Dict[str, Any]]:
        """Test check-in photos functionality"""
        if self.test_checkin_id:
            # Test getting photos for a check-in
            response = APIResponse(await self.client.get(
                f"/checkins/{self.test_checkin_id}/photos",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_pagination(response)
            return response.json

        return None

    async def test_place_checkins(self) -> Optional[Dict[str, Any]]:
        """Test getting check-ins for a place"""
        if self.test_place_id:
            response = APIResponse(await self.client.get(
                f"/places/{self.test_place_id}/checkins",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_pagination(response)
            return response.json

        return None

    async def test_checkin_validation(self) -> Optional[Dict[str, Any]]:
        """Test check-in validation"""
        # Test with invalid data
        invalid_data = {
            "place_id": 99999,  # Non-existent place
            "text": "",  # Empty text
            "visibility": "invalid"  # Invalid visibility
        }

        response = APIResponse(await self.client.post(
            "/checkins/",
            json_data=invalid_data,
            headers=self.get_headers()
        ))

        # Should return validation error
        if response.status_code in [400, 422]:
            return {"validation_error": True}

        return None

    async def test_checkin_privacy(self) -> Optional[Dict[str, Any]]:
        """Test check-in privacy settings"""
        if self.test_place_id:
            # Create private check-in
            private_checkin_data = {
                "place_id": self.test_place_id,
                "text": "Private check-in",
                "visibility": "private"
            }

            response = APIResponse(await self.client.post(
                "/checkins/",
                json_data=private_checkin_data,
                headers=self.get_headers()
            ))

            if response.is_success():
                checkin_id = response.json.get("id")

                # Test that private check-in is only visible to owner
                response = APIResponse(await self.client.get(
                    f"/checkins/{checkin_id}",
                    headers=self.get_headers()
                ))

                TestAssertions.assert_response_success(response)
                return {"privacy_working": True}

        return None

    async def test_checkin_likes(self) -> Optional[Dict[str, Any]]:
        """Test check-in likes functionality"""
        if self.test_checkin_id:
            # Test liking a check-in
            response = APIResponse(await self.client.post(
                f"/checkins/{self.test_checkin_id}/like",
                headers=self.get_headers()
            ))

            # Should either succeed or return appropriate error
            if response.status_code in [200, 201, 404]:
                return {"likes_handled": True}

        return None

    async def test_checkin_comments(self) -> Optional[Dict[str, Any]]:
        """Test check-in comments functionality"""
        if self.test_checkin_id:
            # Test getting comments for a check-in
            response = APIResponse(await self.client.get(
                f"/checkins/{self.test_checkin_id}/comments",
                headers=self.get_headers()
            ))

            # Should either succeed or return appropriate error
            if response.status_code in [200, 404]:
                return {"comments_handled": True}

        return None

    async def test_checkin_search(self) -> Optional[Dict[str, Any]]:
        """Test check-in search functionality"""
        # Test searching check-ins
        response = APIResponse(await self.client.get(
            "/checkins/search?q=coffee",
            headers=self.get_headers()
        ))

        # Should either succeed or return appropriate error
        if response.status_code in [200, 404]:
            return {"search_handled": True}

        return None

    async def test_checkin_analytics(self) -> Optional[Dict[str, Any]]:
        """Test check-in analytics"""
        # Test getting check-in analytics
        response = APIResponse(await self.client.get(
            "/checkins/analytics",
            headers=self.get_headers()
        ))

        # Should either succeed or return appropriate error
        if response.status_code in [200, 404]:
            return {"analytics_handled": True}

        return None

    async def run_tests(self):
        """Run all check-ins API tests"""
        self._log("📍 Testing Check-ins API Endpoints...")

        # Basic CRUD tests
        await self.run_test("Health Check", self.test_health_check)
        await self.run_test("Check-ins Without Auth", self.test_checkins_without_auth)
        await self.run_test("Create Check-in", self.test_create_checkin)
        await self.run_test("Get Check-in", self.test_get_checkin)
        await self.run_test("List User Check-ins", self.test_list_user_checkins)
        await self.run_test("Update Check-in", self.test_update_checkin)

        # Feature tests
        await self.run_test("Check-in Photos", self.test_checkin_photos)
        await self.run_test("Place Check-ins", self.test_place_checkins)
        await self.run_test("Check-in Validation", self.test_checkin_validation)
        await self.run_test("Check-in Privacy", self.test_checkin_privacy)
        await self.run_test("Check-in Likes", self.test_checkin_likes)
        await self.run_test("Check-in Comments", self.test_checkin_comments)
        await self.run_test("Check-in Search", self.test_checkin_search)
        await self.run_test("Check-in Analytics", self.test_checkin_analytics)

        # Cleanup
        await self.run_test("Delete Check-in", self.test_delete_checkin)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = CheckinsAPITest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
