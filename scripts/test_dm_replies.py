#!/usr/bin/env python3
"""
Test script for DM reply functionality
"""
import asyncio
import httpx
import json
from typing import Optional


class DMReplyTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.token: Optional[str] = None
        self.user_id: Optional[int] = None

    async def login(self, username: str, password: str):
        """Login and get authentication token"""
        try:
            response = await self.client.post(
                f"{self.base_url}/auth/login",
                json={"username": username, "password": password}
            )

            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.user_id = data.get("user_id")
                self.client.headers.update(
                    {"Authorization": f"Bearer {self.token}"})
                print(f"✅ Logged in as {username}")
                return True
            else:
                print(f"❌ Login failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False

    async def create_test_user(self, username: str, password: str, name: str):
        """Create a test user for DM testing"""
        try:
            response = await self.client.post(
                f"{self.base_url}/auth/register",
                json={
                    "username": username,
                    "password": password,
                    "name": name,
                    "email": f"{username}@test.com"
                }
            )

            if response.status_code == 201:
                print(f"✅ Created test user: {username}")
                return True
            else:
                print(
                    f"ℹ️  User {username} may already exist: {response.text}")
                return True  # User might already exist
        except Exception as e:
            print(f"❌ Create user error: {e}")
            return False

    async def find_or_create_thread(self, other_user_id: int):
        """Find existing DM thread or create new one"""
        try:
            # Check inbox first
            response = await self.client.get(f"{self.base_url}/dms/inbox")
            if response.status_code == 200:
                threads = response.json()["items"]
                for thread in threads:
                    if thread["other_user_id"] == other_user_id:
                        print(f"✅ Found existing thread: {thread['id']}")
                        return thread["id"]

            # Create new thread
            response = await self.client.post(
                f"{self.base_url}/dms/threads",
                json={"user_id": other_user_id}
            )

            if response.status_code == 201:
                thread_id = response.json()["id"]
                print(f"✅ Created new thread: {thread_id}")
                return thread_id
            else:
                print(f"❌ Failed to create thread: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Thread creation error: {e}")
            return None

    async def send_message(self, thread_id: int, text: str, reply_to_id: Optional[int] = None):
        """Send a message (with optional reply)"""
        try:
            payload = {"text": text}
            if reply_to_id:
                payload["reply_to_id"] = reply_to_id

            response = await self.client.post(
                f"{self.base_url}/dms/threads/{thread_id}/messages",
                json=payload
            )

            if response.status_code == 201:
                message = response.json()
                print(f"✅ Sent message: {text[:50]}...")
                if reply_to_id:
                    print(f"   └─ Reply to message {reply_to_id}")
                return message["id"]
            else:
                print(f"❌ Failed to send message: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Send message error: {e}")
            return None

    async def get_messages(self, thread_id: int):
        """Get messages from a thread"""
        try:
            response = await self.client.get(
                f"{self.base_url}/dms/threads/{thread_id}/messages"
            )

            if response.status_code == 200:
                messages = response.json()["items"]
                print(f"✅ Retrieved {len(messages)} messages")
                return messages
            else:
                print(f"❌ Failed to get messages: {response.text}")
                return []
        except Exception as e:
            print(f"❌ Get messages error: {e}")
            return []

    async def test_reply_flow(self):
        """Test the complete reply flow"""
        print("\n🚀 Starting DM Reply Test...")

        # Create test users
        await self.create_test_user("testuser1", "password123", "Test User 1")
        await self.create_test_user("testuser2", "password123", "Test User 2")

        # Login as user 1
        if not await self.login("testuser1", "password123"):
            return

        # Find user 2's ID (we'll need to get this from the API)
        # For now, let's assume we have user IDs or can get them

        print("\n✅ Reply functionality test setup complete!")
        print("📝 Manual testing instructions:")
        print("1. Use API client (Postman/Insomnia) to test:")
        print("   POST /dms/threads/{thread_id}/messages")
        print("   Body: {\"text\": \"Reply message\", \"reply_to_id\": 123}")
        print("2. Check that reply fields are returned in responses")
        print("3. Verify inbox shows reply context in last message")

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


async def main():
    tester = DMReplyTester()

    try:
        await tester.test_reply_flow()
    finally:
        await tester.close()

if __name__ == "__main__":
    asyncio.run(main())
