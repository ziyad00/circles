"""
Integration tests for Direct Messages API
"""
import asyncio
from typing import Dict, Any, Optional

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse
from ..utils.test_helpers import TestDataFactory, TestAssertions


class DMsAPITest(BaseTest):
    """Test DMs API endpoints"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)
        self.test_thread_id: Optional[int] = None
        self.other_user_id: Optional[int] = None

    async def _setup_test_data(self):
        """Setup test data for DMs"""
        await super()._setup_test_data()

        # Create another test user for DM testing
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

    async def test_health_check(self) -> Optional[Dict[str, Any]]:
        """Test health endpoint"""
        response = APIResponse(await self.client.get("/health"))
        if response.is_success():
            return response.json
        return None

    async def test_open_dm_thread(self) -> Optional[Dict[str, Any]]:
        """Test open DM thread endpoint"""
        if not self.other_user_id:
            return None

        response = APIResponse(await self.client.post(
            "/dms/open",
            json_data={"other_user_id": self.other_user_id},
            headers=self.get_headers()
        ))
        if response.is_success():
            data = response.json
            self.test_thread_id = data.get("id")
            TestAssertions.assert_json_structure(
                response, ["id", "user_a_id", "user_b_id", "status", "created_at"])
            return data
        return None

    async def test_get_dm_thread(self) -> Optional[Dict[str, Any]]:
        """Test get DM thread endpoint"""
        if not self.test_thread_id:
            return None

        response = APIResponse(await self.client.get(
            f"/dms/{self.test_thread_id}",
            headers=self.get_headers()
        ))
        if response.is_success():
            TestAssertions.assert_json_structure(
                response, ["id", "user_a_id", "user_b_id", "status", "created_at"])
            return response.json
        return None

    async def test_send_dm_message(self) -> Optional[Dict[str, Any]]:
        """Test send DM message endpoint"""
        if not self.test_thread_id:
            return None

        message_data = {
            "text": "Hello, this is a test message!",
            "message_type": "text"
        }
        response = APIResponse(await self.client.post(
            f"/dms/{self.test_thread_id}/messages",
            json_data=message_data,
            headers=self.get_headers()
        ))
        if response.is_success():
            data = response.json
            TestAssertions.assert_json_structure(
                response, ["id", "thread_id", "sender_id", "text", "created_at"])
            return data
        return None

    async def test_get_dm_messages(self) -> Optional[Dict[str, Any]]:
        """Test get DM messages endpoint"""
        if not self.test_thread_id:
            return None

        response = APIResponse(await self.client.get(
            f"/dms/{self.test_thread_id}/messages",
            headers=self.get_headers()
        ))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_dm_threads_list(self) -> Optional[Dict[str, Any]]:
        """Test DM threads list endpoint"""
        response = APIResponse(await self.client.get(
            "/dms/",
            headers=self.get_headers()
        ))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_dm_requests_list(self) -> Optional[Dict[str, Any]]:
        """Test DM requests list endpoint"""
        response = APIResponse(await self.client.get(
            "/dms/requests",
            headers=self.get_headers()
        ))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_send_dm_request(self) -> Optional[Dict[str, Any]]:
        """Test send DM request endpoint"""
        if not self.other_user_id:
            return None

        request_data = {
            "recipient_id": self.other_user_id,
            "text": "Hello, I'd like to chat with you!"
        }
        response = APIResponse(await self.client.post(
            "/dms/requests",
            json_data=request_data,
            headers=self.get_headers()
        ))
        if response.is_success():
            data = response.json
            TestAssertions.assert_json_structure(
                response, ["id", "user_a_id", "user_b_id", "status", "created_at"])
            return data
        return None

    async def test_dm_thread_archive(self) -> Optional[Dict[str, Any]]:
        """Test DM thread archive endpoint"""
        if not self.test_thread_id:
            return None

        archive_data = {"archived": True}
        response = APIResponse(await self.client.patch(
            f"/dms/{self.test_thread_id}/archive",
            json_data=archive_data,
            headers=self.get_headers()
        ))
        if response.is_success():
            return response.json
        return None

    async def test_dm_thread_mute(self) -> Optional[Dict[str, Any]]:
        """Test DM thread mute endpoint"""
        if not self.test_thread_id:
            return None

        mute_data = {"muted": True}
        response = APIResponse(await self.client.patch(
            f"/dms/{self.test_thread_id}/mute",
            json_data=mute_data,
            headers=self.get_headers()
        ))
        if response.is_success():
            return response.json
        return None

    async def test_dm_thread_pin(self) -> Optional[Dict[str, Any]]:
        """Test DM thread pin endpoint"""
        if not self.test_thread_id:
            return None

        pin_data = {"pinned": True}
        response = APIResponse(await self.client.patch(
            f"/dms/{self.test_thread_id}/pin",
            json_data=pin_data,
            headers=self.get_headers()
        ))
        if response.is_success():
            return response.json
        return None

    async def test_dm_unread_count(self) -> Optional[Dict[str, Any]]:
        """Test DM unread count endpoint"""
        response = APIResponse(await self.client.get(
            "/dms/unread-count",
            headers=self.get_headers()
        ))
        if response.is_success():
            data = response.json
            assert "unread" in data, "Response should contain unread count"
            return data
        return None

    async def test_dms_without_auth(self) -> Optional[Dict[str, Any]]:
        """Test DMs endpoints without authentication (should fail)"""
        response = APIResponse(await self.client.get("/dms/"))
        if response.status_code == 401:
            return {"unauthorized": True}
        return None

    async def run_tests(self):
        """Run all DMs tests"""
        self._log("💬 Testing DMs API Endpoints...")

        # Test 1: Health check
        await self.run_test("Health Check", self.test_health_check)

        # Test 2: DMs without auth (should fail)
        await self.run_test("DMs Without Auth", self.test_dms_without_auth)

        # Test 3: DM threads list
        await self.run_test("DM Threads List", self.test_dm_threads_list)

        # Test 4: DM requests list
        await self.run_test("DM Requests List", self.test_dm_requests_list)

        # Test 5: Send DM request
        await self.run_test("Send DM Request", self.test_send_dm_request)

        # Test 6: Open DM thread
        await self.run_test("Open DM Thread", self.test_open_dm_thread)

        if self.test_thread_id:
            # Test 7: Get DM thread
            await self.run_test("Get DM Thread", self.test_get_dm_thread)

            # Test 8: Send DM message
            await self.run_test("Send DM Message", self.test_send_dm_message)

            # Test 9: Get DM messages
            await self.run_test("Get DM Messages", self.test_get_dm_messages)

            # Test 10: DM thread operations
            await self.run_test("DM Thread Archive", self.test_dm_thread_archive)
            await self.run_test("DM Thread Mute", self.test_dm_thread_mute)
            await self.run_test("DM Thread Pin", self.test_dm_thread_pin)

        # Test 11: Unread count
        await self.run_test("DM Unread Count", self.test_dm_unread_count)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = DMsAPITest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
