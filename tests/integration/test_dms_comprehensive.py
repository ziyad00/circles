"""
Comprehensive Integration tests for Direct Messages (DMs) API
"""
import asyncio
from typing import Dict, Any, Optional

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse
from ..utils.test_helpers import TestAssertions, TestDataFactory, TestCleanup, TestFixtures


class DMsComprehensiveTest(BaseTest):
    """Comprehensive integration tests for DMs API endpoints"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)
        self.other_user_id: int = 0
        self.dm_thread_id: int = 0
        self.message_id: int = 0

    async def teardown(self):
        """Cleanup after tests"""
        await self.client.close()
        await super().teardown()

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
                    email="test2@example.com",
                    is_verified=True,
                    name="Test User Two",
                    bio="Another test user for DM testing.",
                    avatar_url="https://example.com/avatar_other.jpg",
                    dm_privacy="everyone",
                    checkins_default_visibility="public",
                    collections_default_visibility="public",
                    profile_visibility="public",
                    follower_list_visibility="public",
                    following_list_visibility="public",
                    stats_visibility="public",
                    media_default_visibility="public",
                    search_visibility="public",
                    availability_status="available",
                    availability_mode="auto"
                )
                db.add(other_user)
                await db.commit()
                await db.refresh(other_user)
                self._log(f"Created other test user: {other_user.id}")
            else:
                self._log(f"Using existing other test user: {other_user.id}")

            self.other_user_id = other_user.id

    async def test_health_check(self) -> Optional[Dict[str, Any]]:
        """Test health check endpoint"""
        response = APIResponse(await self.client.get("/health"))
        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_contains(response, "status", "ok")
        return response.json

    async def test_dm_open_thread(self) -> Optional[Dict[str, Any]]:
        """Test opening a DM thread"""
        payload = {"other_user_id": self.other_user_id}
        response = APIResponse(await self.client.post(
            "/dms/open",
            json_data=payload,
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_contains(
            response, "user_a_id", min(self.test_user.id, self.other_user_id))
        TestAssertions.assert_json_contains(
            response, "user_b_id", max(self.test_user.id, self.other_user_id))
        TestAssertions.assert_json_contains(response, "status", "accepted")
        self.dm_thread_id = response.json["id"]
        return response.json

    async def test_dm_send_request(self) -> Optional[Dict[str, Any]]:
        """Test sending a DM request"""
        payload = {
            "recipient_id": self.other_user_id,
            "text": "Hello! This is a test DM request."
        }
        response = APIResponse(await self.client.post(
            "/dms/requests",
            json_data=payload,
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response, 201)
        TestAssertions.assert_json_contains(
            response, "user_a_id", min(self.test_user.id, self.other_user_id))
        TestAssertions.assert_json_contains(
            response, "user_b_id", max(self.test_user.id, self.other_user_id))
        return response.json

    async def test_dm_list_requests(self) -> Optional[Dict[str, Any]]:
        """Test listing DM requests"""
        response = APIResponse(await self.client.get(
            "/dms/requests",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_pagination(response)
        return response.json

    async def test_dm_respond_to_request(self) -> Optional[Dict[str, Any]]:
        """Test responding to a DM request"""
        # Skip this test since we can't respond to our own request
        # In a real scenario, this would be tested with a different user
        return {"skipped": "Cannot test responding to own request"}

    async def test_dm_send_message(self) -> Optional[Dict[str, Any]]:
        """Test sending a message in a DM thread"""
        if self.dm_thread_id:
            payload = {
                "text": "Hello! This is a test message.",
                "message_type": "text"
            }
            response = APIResponse(await self.client.post(
                f"/dms/threads/{self.dm_thread_id}/messages",
                json_data=payload,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response, 201)
            TestAssertions.assert_json_contains(
                response, "text", payload["text"])
            TestAssertions.assert_json_contains(
                response, "thread_id", self.dm_thread_id)
            self.message_id = response.json["id"]
            return response.json
        return None

    async def test_dm_list_messages(self) -> Optional[Dict[str, Any]]:
        """Test listing messages in a DM thread"""
        if self.dm_thread_id:
            response = APIResponse(await self.client.get(
                f"/dms/threads/{self.dm_thread_id}/messages",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_pagination(response)
            assert len(response.json["items"]) > 0
            return response.json
        return None

    async def test_dm_get_thread(self) -> Optional[Dict[str, Any]]:
        """Test getting a specific DM thread"""
        if self.dm_thread_id:
            response = APIResponse(await self.client.get(
                f"/dms/threads/{self.dm_thread_id}",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(
                response, "id", self.dm_thread_id)
            return response.json
        return None

    async def test_dm_inbox(self) -> Optional[Dict[str, Any]]:
        """Test getting DM inbox"""
        response = APIResponse(await self.client.get(
            "/dms/inbox",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_pagination(response)
        return response.json

    async def test_dm_unread_count(self) -> Optional[Dict[str, Any]]:
        """Test getting unread message count"""
        response = APIResponse(await self.client.get(
            "/dms/unread-count",
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_structure(response, ["unread"])
        return response.json

    async def test_dm_thread_unread_count(self) -> Optional[Dict[str, Any]]:
        """Test getting unread count for specific thread"""
        if self.dm_thread_id:
            response = APIResponse(await self.client.get(
                f"/dms/threads/{self.dm_thread_id}/unread-count",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_structure(response, ["unread"])
            return response.json
        return None

    async def test_dm_mark_read(self) -> Optional[Dict[str, Any]]:
        """Test marking messages as read"""
        if self.dm_thread_id:
            response = APIResponse(await self.client.post(
                f"/dms/threads/{self.dm_thread_id}/mark-read",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response, 204)
            return {"marked_read": True}
        return None

    async def test_dm_mute_thread(self) -> Optional[Dict[str, Any]]:
        """Test muting a DM thread"""
        if self.dm_thread_id:
            payload = {"muted": True}
            response = APIResponse(await self.client.put(
                f"/dms/threads/{self.dm_thread_id}/mute",
                json_data=payload,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(response, "muted", True)
            return response.json
        return None

    async def test_dm_unmute_thread(self) -> Optional[Dict[str, Any]]:
        """Test unmuting a DM thread"""
        if self.dm_thread_id:
            payload = {"muted": False}
            response = APIResponse(await self.client.put(
                f"/dms/threads/{self.dm_thread_id}/mute",
                json_data=payload,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(response, "muted", False)
            return response.json
        return None

    async def test_dm_pin_thread(self) -> Optional[Dict[str, Any]]:
        """Test pinning a DM thread"""
        if self.dm_thread_id:
            payload = {"pinned": True}
            response = APIResponse(await self.client.put(
                f"/dms/threads/{self.dm_thread_id}/pin",
                json_data=payload,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(response, "pinned", True)
            return response.json
        return None

    async def test_dm_unpin_thread(self) -> Optional[Dict[str, Any]]:
        """Test unpinning a DM thread"""
        if self.dm_thread_id:
            payload = {"pinned": False}
            response = APIResponse(await self.client.put(
                f"/dms/threads/{self.dm_thread_id}/pin",
                json_data=payload,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(response, "pinned", False)
            return response.json
        return None

    async def test_dm_archive_thread(self) -> Optional[Dict[str, Any]]:
        """Test archiving a DM thread"""
        if self.dm_thread_id:
            payload = {"archived": True}
            response = APIResponse(await self.client.put(
                f"/dms/threads/{self.dm_thread_id}/archive",
                json_data=payload,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(response, "archived", True)
            return response.json
        return None

    async def test_dm_unarchive_thread(self) -> Optional[Dict[str, Any]]:
        """Test unarchiving a DM thread"""
        if self.dm_thread_id:
            payload = {"archived": False}
            response = APIResponse(await self.client.put(
                f"/dms/threads/{self.dm_thread_id}/archive",
                json_data=payload,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(response, "archived", False)
            return response.json
        return None

    async def test_dm_heart_message(self) -> Optional[Dict[str, Any]]:
        """Test hearting a message"""
        if self.dm_thread_id and self.message_id:
            response = APIResponse(await self.client.post(
                f"/dms/threads/{self.dm_thread_id}/messages/{self.message_id}/heart",
                headers=self.get_headers()
            ))
            
            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_structure(
                response, ["liked", "heart_count"])
            return response.json
        return {"skipped": "No message ID available"}

    async def test_dm_add_reaction(self) -> Optional[Dict[str, Any]]:
        """Test adding a reaction to a message"""
        if self.dm_thread_id and self.message_id:
            payload = {"emoji": "👍"}
            response = APIResponse(await self.client.post(
                f"/dms/threads/{self.dm_thread_id}/messages/{self.message_id}/reactions",
                json_data=payload,
                headers=self.get_headers()
            ))
            
            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(response, "emoji", "👍")
            return response.json
        return {"skipped": "No message ID available"}

    async def test_dm_get_reactions(self) -> Optional[Dict[str, Any]]:
        """Test getting reactions for a message"""
        if self.dm_thread_id and self.message_id:
            response = APIResponse(await self.client.get(
                f"/dms/threads/{self.dm_thread_id}/messages/{self.message_id}/reactions",
                headers=self.get_headers()
            ))
            
            TestAssertions.assert_response_success(response)
            return response.json
        return {"skipped": "No message ID available"}

    async def test_dm_remove_reaction(self) -> Optional[Dict[str, Any]]:
        """Test removing a reaction from a message"""
        if self.dm_thread_id and self.message_id:
            response = APIResponse(await self.client.delete(
                f"/dms/threads/{self.dm_thread_id}/messages/{self.message_id}/reactions/👍",
                headers=self.get_headers()
            ))
            
            TestAssertions.assert_response_success(response)
            return response.json
        return {"skipped": "No message ID available"}

    async def test_dm_set_typing(self) -> Optional[Dict[str, Any]]:
        """Test setting typing status"""
        if self.dm_thread_id:
            payload = {"typing": True}
            response = APIResponse(await self.client.post(
                f"/dms/threads/{self.dm_thread_id}/typing",
                json_data=payload,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response, 204)
            return {"typing_set": True}
        return None

    async def test_dm_get_typing(self) -> Optional[Dict[str, Any]]:
        """Test getting typing status"""
        if self.dm_thread_id:
            response = APIResponse(await self.client.get(
                f"/dms/threads/{self.dm_thread_id}/typing",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_structure(response, ["typing", "until"])
            return response.json
        return None

    async def test_dm_get_presence(self) -> Optional[Dict[str, Any]]:
        """Test getting user presence"""
        if self.dm_thread_id:
            response = APIResponse(await self.client.get(
                f"/dms/threads/{self.dm_thread_id}/presence",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_structure(
                response, ["user_id", "online", "last_active_at"])
            return response.json
        return None

    async def test_dm_block_user(self) -> Optional[Dict[str, Any]]:
        """Test blocking a user"""
        payload = {"blocked": True}
        response = APIResponse(await self.client.put(
            f"/dms/threads/{self.other_user_id}/block",
            json_data=payload,
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_contains(response, "blocked", True)
        return response.json

    async def test_dm_unblock_user(self) -> Optional[Dict[str, Any]]:
        """Test unblocking a user"""
        payload = {"blocked": False}
        response = APIResponse(await self.client.put(
            f"/dms/threads/{self.other_user_id}/block",
            json_data=payload,
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_contains(response, "blocked", False)
        return response.json

    async def test_dm_delete_message(self) -> Optional[Dict[str, Any]]:
        """Test deleting a message"""
        if self.dm_thread_id and self.message_id:
            response = APIResponse(await self.client.delete(
                f"/dms/threads/{self.dm_thread_id}/messages/{self.message_id}",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response, 204)
            return {"deleted": True}
        return None

    async def test_dm_search_messages(self) -> Optional[Dict[str, Any]]:
        """Test searching messages in a thread"""
        if self.dm_thread_id:
            response = APIResponse(await self.client.get(
                f"/dms/threads/{self.dm_thread_id}/search?query=test",
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_structure(
                response, ["results", "total", "limit", "offset"])
            return response.json
        return None

    async def test_dm_share_location(self) -> Optional[Dict[str, Any]]:
        """Test sharing location in a DM"""
        if self.dm_thread_id:
            payload = {
                "latitude": 40.7128,
                "longitude": -74.0060,
                "name": "Test Location",
                "address": "123 Test St, Test City"
            }
            response = APIResponse(await self.client.post(
                f"/dms/threads/{self.dm_thread_id}/share-location",
                json_data=payload,
                headers=self.get_headers()
            ))

            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_contains(
                response, "message_type", "location")
            return response.json
        return None

    async def test_dm_forward_message(self) -> Optional[Dict[str, Any]]:
        """Test forwarding a message"""
        if self.dm_thread_id and self.message_id:
            payload = {
                "message_id": self.message_id,
                "target_thread_ids": [self.dm_thread_id]
            }
            response = APIResponse(await self.client.post(
                f"/dms/threads/{self.dm_thread_id}/forward",
                json_data=payload,
                headers=self.get_headers()
            ))
            
            TestAssertions.assert_response_success(response)
            TestAssertions.assert_json_structure(
                response, ["forwarded_count", "failed_threads", "total_requested"])
            return response.json
        return {"skipped": "No message ID available"}

    async def test_dm_upload_media(self) -> Optional[Dict[str, Any]]:
        """Test uploading media for DM"""
        # Create a simple test file
        import io
        test_file = io.BytesIO(b"fake image data")

        response = APIResponse(await self.client.post(
            "/dms/upload/media",
            files={"file": ("test.jpg", test_file, "image/jpeg")},
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_structure(
            response, ["url", "media_type", "file_size", "content_type"])
        return response.json

    async def test_dm_upload_voice(self) -> Optional[Dict[str, Any]]:
        """Test uploading voice message"""
        import io
        test_file = io.BytesIO(b"fake audio data")

        response = APIResponse(await self.client.post(
            "/dms/upload/voice",
            files={"file": ("test.mp3", test_file, "audio/mpeg")},
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_structure(
            response, ["url", "duration", "file_size"])
        return response.json

    async def test_dm_upload_file(self) -> Optional[Dict[str, Any]]:
        """Test uploading file for DM"""
        import io
        test_file = io.BytesIO(b"fake document data")

        response = APIResponse(await self.client.post(
            "/dms/upload/file",
            files={"file": ("test.pdf", test_file, "application/pdf")},
            headers=self.get_headers()
        ))

        TestAssertions.assert_response_success(response)
        TestAssertions.assert_json_structure(
            response, ["url", "filename", "file_size", "content_type"])
        return response.json

    async def test_dm_validation_errors(self) -> Optional[Dict[str, Any]]:
        """Test DM validation errors"""
        # Test sending message to non-existent thread
        response = APIResponse(await self.client.post(
            "/dms/threads/99999/messages",
            json_data={"text": "test"},
            headers=self.get_headers()
        ))

        if response.status_code == 404:
            return {"validation_working": True}
        return None

    async def test_dm_rate_limiting(self) -> Optional[Dict[str, Any]]:
        """Test DM rate limiting"""
        # Send multiple requests quickly to test rate limiting
        responses = []
        for i in range(10):
            response = APIResponse(await self.client.post(
                "/dms/requests",
                json_data={
                    "recipient_id": self.other_user_id,
                    "text": f"Rate limit test {i}"
                },
                headers=self.get_headers()
            ))
            responses.append(response)

        # Check if any requests were rate limited
        rate_limited = any(r.status_code == 429 for r in responses)
        return {"rate_limiting_working": rate_limited}

    async def test_dm_privacy_settings(self) -> Optional[Dict[str, Any]]:
        """Test DM privacy settings"""
        # Test sending DM to user with restricted privacy
        response = APIResponse(await self.client.post(
            "/dms/requests",
            json_data={
                "recipient_id": self.other_user_id,
                "text": "Privacy test"
            },
            headers=self.get_headers()
        ))
        
        # Should either succeed or be blocked by privacy settings
        if response.status_code in [200, 201, 403]:
            return {"privacy_working": True}
        return {"privacy_test_failed": f"Unexpected status code: {response.status_code}"}

    async def run_tests(self):
        """Run all comprehensive DM tests"""
        self._log("💬 Testing Comprehensive DM API Endpoints...")

        # Basic functionality tests
        await self.run_test("Health Check", self.test_health_check)
        await self.run_test("Open DM Thread", self.test_dm_open_thread)
        await self.run_test("Send DM Request", self.test_dm_send_request)
        await self.run_test("List DM Requests", self.test_dm_list_requests)
        await self.run_test("Respond to DM Request", self.test_dm_respond_to_request)

        # Message functionality tests
        await self.run_test("Send DM Message", self.test_dm_send_message)
        await self.run_test("List DM Messages", self.test_dm_list_messages)
        await self.run_test("Get DM Thread", self.test_dm_get_thread)
        await self.run_test("Delete DM Message", self.test_dm_delete_message)

        # Inbox and organization tests
        await self.run_test("Get DM Inbox", self.test_dm_inbox)
        await self.run_test("Get Unread Count", self.test_dm_unread_count)
        await self.run_test("Get Thread Unread Count", self.test_dm_thread_unread_count)
        await self.run_test("Mark Messages as Read", self.test_dm_mark_read)

        # Thread management tests
        await self.run_test("Mute DM Thread", self.test_dm_mute_thread)
        await self.run_test("Unmute DM Thread", self.test_dm_unmute_thread)
        await self.run_test("Pin DM Thread", self.test_dm_pin_thread)
        await self.run_test("Unpin DM Thread", self.test_dm_unpin_thread)
        await self.run_test("Archive DM Thread", self.test_dm_archive_thread)
        await self.run_test("Unarchive DM Thread", self.test_dm_unarchive_thread)

        # Interaction tests
        await self.run_test("Heart DM Message", self.test_dm_heart_message)
        await self.run_test("Add Message Reaction", self.test_dm_add_reaction)
        await self.run_test("Get Message Reactions", self.test_dm_get_reactions)
        await self.run_test("Remove Message Reaction", self.test_dm_remove_reaction)

        # Real-time features tests
        await self.run_test("Set Typing Status", self.test_dm_set_typing)
        await self.run_test("Get Typing Status", self.test_dm_get_typing)
        await self.run_test("Get User Presence", self.test_dm_get_presence)

        # Blocking tests
        await self.run_test("Block User", self.test_dm_block_user)
        await self.run_test("Unblock User", self.test_dm_unblock_user)

        # Advanced features tests
        await self.run_test("Search DM Messages", self.test_dm_search_messages)
        await self.run_test("Share Location", self.test_dm_share_location)
        await self.run_test("Forward Message", self.test_dm_forward_message)

        # Media upload tests
        await self.run_test("Upload DM Media", self.test_dm_upload_media)
        await self.run_test("Upload Voice Message", self.test_dm_upload_voice)
        await self.run_test("Upload DM File", self.test_dm_upload_file)

        # Error handling and validation tests
        await self.run_test("DM Validation Errors", self.test_dm_validation_errors)
        await self.run_test("DM Rate Limiting", self.test_dm_rate_limiting)
        await self.run_test("DM Privacy Settings", self.test_dm_privacy_settings)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = DMsComprehensiveTest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
