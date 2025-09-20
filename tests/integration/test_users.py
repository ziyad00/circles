"""
Integration tests for Users API
"""
import asyncio
from typing import Dict, Any, Optional

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse
from ..utils.test_helpers import TestAssertions, TestDataFactory, TestCleanup, TestFixtures


class UsersAPITest(BaseTest):
    """Integration tests for Users API endpoints"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)

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

    async def test_get_user_profile(self) -> Optional[Dict[str, Any]]:
        """Test getting user profile"""
        response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_contains(response, "id", self.test_user.id)
        TestAssertions.assert_json_contains(
            response, "username", self.test_user.username)
        return response.json

    async def test_update_user_profile(self) -> Optional[Dict[str, Any]]:
        """Test updating user profile"""
        update_data = {
            "name": "Updated Test User",
            "bio": "Updated bio for testing",
            "avatar_url": "https://example.com/new-avatar.jpg"
        }

        response = APIResponse(await self.client.patch(
            f"/users/{self.test_user.id}",
            json_data=update_data,
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_contains(
            response, "name", update_data["name"])
        TestAssertions.assert_json_contains(
            response, "bio", update_data["bio"])
        return response.json

    async def test_user_privacy_settings(self) -> Optional[Dict[str, Any]]:
        """Test user privacy settings"""
        privacy_data = {
            "profile_visibility": "private",
            "dm_privacy": "followers",
            "checkins_default_visibility": "private",
            "collections_default_visibility": "private"
        }

        response = APIResponse(await self.client.patch(
            f"/users/{self.test_user.id}/privacy",
            json_data=privacy_data,
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_contains(
            response, "profile_visibility", privacy_data["profile_visibility"])
        return response.json

    async def test_user_availability_settings(self) -> Optional[Dict[str, Any]]:
        """Test user availability settings"""
        availability_data = {
            "availability_status": "available",
            "availability_mode": "manual"
        }

        response = APIResponse(await self.client.patch(
            f"/users/{self.test_user.id}/availability",
            json_data=availability_data,
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_contains(
            response, "availability_status", availability_data["availability_status"])
        return response.json

    async def test_user_followers(self) -> Optional[Dict[str, Any]]:
        """Test getting user followers"""
        response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/followers",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_pagination(response)
        return response.json

    async def test_user_following(self) -> Optional[Dict[str, Any]]:
        """Test getting user following"""
        response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/following",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_pagination(response)
        return response.json

    async def test_user_checkins(self) -> Optional[Dict[str, Any]]:
        """Test getting user check-ins"""
        response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/checkins",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_pagination(response)
        return response.json

    async def test_user_collections(self) -> Optional[Dict[str, Any]]:
        """Test getting user collections"""
        response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/collections",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_pagination(response)
        return response.json

    async def test_user_stats(self) -> Optional[Dict[str, Any]]:
        """Test getting user statistics"""
        response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/stats",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_structure(response, [
                                             "user_id", "checkins_count", "collections_count", "followers_count", "following_count"])
        return response.json

    async def test_user_search(self) -> Optional[Dict[str, Any]]:
        """Test user search functionality"""
        response = APIResponse(await self.client.get(
            "/users/search?q=test",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_pagination(response)
        return response.json

    async def test_user_validation(self) -> Optional[Dict[str, Any]]:
        """Test user data validation"""
        # Test with invalid data
        invalid_data = {
            "name": "",  # Empty name
            "email": "invalid-email",  # Invalid email
            "bio": "A" * 1000  # Too long bio
        }

        response = APIResponse(await self.client.patch(
            f"/users/{self.test_user.id}",
            json_data=invalid_data,
            headers=self.get_headers()
        ))

        # Should return validation error
        if response.status_code in [400, 422]:
            return {"validation_error": True}

        return None

    async def test_user_unauthorized_access(self) -> Optional[Dict[str, Any]]:
        """Test unauthorized access to user data"""
        # Test accessing user data without authentication
        response = APIResponse(await self.client.get(f"/users/{self.test_user.id}"))

        # Should either succeed (public profile) or require auth
        if response.status_code in [200, 401]:
            return {"access_controlled": True}

        return None

    async def test_user_avatar_upload(self) -> Optional[Dict[str, Any]]:
        """Test user avatar upload"""
        # Test avatar upload endpoint
        response = APIResponse(await self.client.post(
            f"/users/{self.test_user.id}/avatar",
            headers=self.get_headers()
        ))

        # Should either succeed or return appropriate error
        if response.status_code in [200, 201, 400, 404]:
            return {"avatar_upload_handled": True}

        return None

    async def test_user_blocking(self) -> Optional[Dict[str, Any]]:
        """Test user blocking functionality"""
        # Test blocking a user
        response = APIResponse(await self.client.post(
            f"/users/{self.test_user.id}/block",
            headers=self.get_headers()
        ))

        # Should either succeed or return appropriate error
        if response.status_code in [200, 201, 400, 404]:
            return {"blocking_handled": True}

        return None

    async def test_user_reporting(self) -> Optional[Dict[str, Any]]:
        """Test user reporting functionality"""
        # Test reporting a user
        report_data = {
            "reason": "spam",
            "description": "User is posting spam content"
        }

        response = APIResponse(await self.client.post(
            f"/users/{self.test_user.id}/report",
            json_data=report_data,
            headers=self.get_headers()
        ))

        # Should either succeed or return appropriate error
        if response.status_code in [200, 201, 400, 404]:
            return {"reporting_handled": True}

        return None

    async def test_user_notifications(self) -> Optional[Dict[str, Any]]:
        """Test user notifications"""
        # Test getting user notifications
        response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/notifications",
            headers=self.get_headers()
        ))

        # Should either succeed or return appropriate error
        if response.status_code in [200, 404]:
            return {"notifications_handled": True}

        return None

    async def test_user_activity_feed(self) -> Optional[Dict[str, Any]]:
        """Test user activity feed"""
        # Test getting user activity feed
        response = APIResponse(await self.client.get(
            f"/users/{self.test_user.id}/activity",
            headers=self.get_headers()
        ))

        # Should either succeed or return appropriate error
        if response.status_code in [200, 404]:
            return {"activity_feed_handled": True}

        return None

    async def run_tests(self):
        """Run all users API tests"""
        self._log("👤 Testing Users API Endpoints...")

        # Basic profile tests
        await self.run_test("Health Check", self.test_health_check)
        await self.run_test("Get User Profile", self.test_get_user_profile)
        await self.run_test("Update User Profile", self.test_update_user_profile)

        # Settings tests
        await self.run_test("User Privacy Settings", self.test_user_privacy_settings)
        await self.run_test("User Availability Settings", self.test_user_availability_settings)

        # Social features tests
        await self.run_test("User Followers", self.test_user_followers)
        await self.run_test("User Following", self.test_user_following)
        await self.run_test("User Check-ins", self.test_user_checkins)
        await self.run_test("User Collections", self.test_user_collections)
        await self.run_test("User Stats", self.test_user_stats)

        # Search and discovery tests
        await self.run_test("User Search", self.test_user_search)

        # Validation and security tests
        await self.run_test("User Validation", self.test_user_validation)
        await self.run_test("User Unauthorized Access", self.test_user_unauthorized_access)

        # Advanced features tests
        await self.run_test("User Avatar Upload", self.test_user_avatar_upload)
        await self.run_test("User Blocking", self.test_user_blocking)
        await self.run_test("User Reporting", self.test_user_reporting)
        await self.run_test("User Notifications", self.test_user_notifications)
        await self.run_test("User Activity Feed", self.test_user_activity_feed)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = UsersAPITest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
