#!/usr/bin/env python3
"""
Comprehensive test script for Circles application features.
Run this script to test all major functionality.
"""

import asyncio
import httpx
import json
from typing import Dict, Any


class CirclesTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
        self.test_results = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def log_test(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"   {details}")
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })

    async def test_health_check(self):
        """Test health check endpoint"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                data = response.json()
                self.log_test("Health Check", True,
                              f"Status: {data.get('status')}")
            else:
                self.log_test("Health Check", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Health Check", False, f"Error: {str(e)}")

    async def test_metrics_endpoint(self):
        """Test metrics endpoint"""
        try:
            response = await self.client.get(f"{self.base_url}/metrics")
            if response.status_code == 200:
                self.log_test("Metrics Endpoint", True, "Metrics accessible")
            else:
                self.log_test("Metrics Endpoint", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Metrics Endpoint", False, f"Error: {str(e)}")

    async def test_auth_otp_request(self):
        """Test OTP request"""
        try:
            response = await self.client.post(
                f"{self.base_url}/auth/request-otp",
                json={"email": "test@example.com"}
            )
            if response.status_code == 200:
                data = response.json()
                self.log_test("OTP Request", True,
                              f"Message: {data.get('message', '')[:50]}...")
            else:
                self.log_test("OTP Request", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("OTP Request", False, f"Error: {str(e)}")

    async def test_auth_otp_verify(self):
        """Test OTP verification"""
        try:
            # First request OTP
            await self.client.post(
                f"{self.base_url}/auth/request-otp",
                json={"email": "verify@example.com"}
            )

            # Then verify with test OTP
            response = await self.client.post(
                f"{self.base_url}/auth/verify-otp",
                json={"email": "verify@example.com", "otp_code": "123456"}
            )
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.log_test("OTP Verification", True, "Token received")
                    return data["access_token"]
                else:
                    self.log_test("OTP Verification", False,
                                  "No token in response")
            else:
                self.log_test("OTP Verification", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("OTP Verification", False, f"Error: {str(e)}")
        return None

    async def test_onboarding_phone_otp(self):
        """Test phone OTP request"""
        try:
            response = await self.client.post(
                f"{self.base_url}/onboarding/request-otp",
                json={"phone": "+1234567890"}
            )
            if response.status_code == 200:
                data = response.json()
                self.log_test("Phone OTP Request", True,
                              f"Message: {data.get('message', '')[:50]}...")
            else:
                self.log_test("Phone OTP Request", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Phone OTP Request", False, f"Error: {str(e)}")

    async def test_onboarding_phone_verify(self):
        """Test phone OTP verification"""
        try:
            # First request phone OTP
            await self.client.post(
                f"{self.base_url}/onboarding/request-otp",
                json={"phone": "+1234567890"}
            )

            # Then verify
            response = await self.client.post(
                f"{self.base_url}/onboarding/verify-otp",
                json={"phone": "+1234567890", "otp_code": "123456"}
            )
            if response.status_code == 200:
                data = response.json()
                self.log_test("Phone OTP Verification", True,
                              f"Message: {data.get('message', '')[:50]}...")
            else:
                self.log_test("Phone OTP Verification", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Phone OTP Verification", False, f"Error: {str(e)}")

    async def test_username_availability(self):
        """Test username availability check"""
        try:
            response = await self.client.post(f"{self.base_url}/onboarding/check-username", json={"username": "testuser123"})
            if response.status_code == 200:
                data = response.json()
                self.log_test("Username Availability", True,
                              f"Available: {data.get('available')}")
            else:
                self.log_test("Username Availability", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Username Availability", False, f"Error: {str(e)}")

    async def test_user_setup(self):
        """Test user setup completion"""
        try:
            # First verify phone
            await self.client.post(
                f"{self.base_url}/onboarding/request-otp",
                json={"phone": "+1234567890"}
            )
            await self.client.post(
                f"{self.base_url}/onboarding/verify-otp",
                json={"phone": "+1234567890", "otp_code": "123456"}
            )

            # Then complete setup
            setup_data = {
                "username": "testuser123",
                "first_name": "Test",
                "last_name": "User",
                "interests": ["food", "travel"]
            }
            response = await self.client.post(
                f"{self.base_url}/onboarding/complete-setup",
                json=setup_data
            )
            if response.status_code == 200:
                data = response.json()
                self.log_test("User Setup", True,
                              f"Message: {data.get('message', '')[:50]}...")
            else:
                self.log_test("User Setup", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("User Setup", False, f"Error: {str(e)}")

    async def test_authenticated_endpoints(self, token: str):
        """Test endpoints that require authentication"""
        headers = {"Authorization": f"Bearer {token}"}

        # Test getting user profile
        try:
            response = await self.client.get(f"{self.base_url}/users/me", headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Get User Profile", True,
                              f"Email: {data.get('email', 'N/A')}")
            else:
                self.log_test("Get User Profile", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Get User Profile", False, f"Error: {str(e)}")

        # Test updating user profile
        try:
            update_data = {"display_name": "Updated Name",
                           "bio": "Updated bio"}
            response = await self.client.put(f"{self.base_url}/users/me", json=update_data, headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Update User Profile", True,
                              f"Name: {data.get('display_name', 'N/A')}")
            else:
                self.log_test("Update User Profile", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Update User Profile", False, f"Error: {str(e)}")

        # Test getting privacy settings
        try:
            response = await self.client.get(f"{self.base_url}/settings/privacy", headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Get Privacy Settings", True,
                              f"DM Privacy: {data.get('dm_privacy', 'N/A')}")
            else:
                self.log_test("Get Privacy Settings", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Get Privacy Settings", False, f"Error: {str(e)}")

        # Test updating privacy settings
        try:
            settings_data = {
                "dm_privacy": "followers_only",
                "checkins_default_visibility": "public",
                "collections_default_visibility": "private"
            }
            response = await self.client.put(f"{self.base_url}/settings/privacy", json=settings_data, headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Update Privacy Settings", True,
                              f"DM Privacy: {data.get('dm_privacy', 'N/A')}")
            else:
                self.log_test("Update Privacy Settings", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Update Privacy Settings", False, f"Error: {str(e)}")

        # Test getting notification preferences
        try:
            response = await self.client.get(f"{self.base_url}/settings/notifications", headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Get Notification Preferences", True,
                              f"DM Messages: {data.get('dm_messages', 'N/A')}")
            else:
                self.log_test("Get Notification Preferences", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Get Notification Preferences",
                          False, f"Error: {str(e)}")

        # Test creating support ticket
        try:
            ticket_data = {
                "subject": "Test Issue",
                "message": "This is a test support ticket"
            }
            response = await self.client.post(f"{self.base_url}/support/tickets", json=ticket_data, headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Create Support Ticket", True,
                              f"Subject: {data.get('subject', 'N/A')}")
            else:
                self.log_test("Create Support Ticket", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Create Support Ticket", False, f"Error: {str(e)}")

        # Test getting support tickets
        try:
            response = await self.client.get(f"{self.base_url}/support/tickets", headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Get Support Tickets", True,
                              f"Count: {len(data.get('items', []))}")
            else:
                self.log_test("Get Support Tickets", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Get Support Tickets", False, f"Error: {str(e)}")

    async def test_places_endpoints(self, token: str):
        """Test place-related endpoints"""
        headers = {"Authorization": f"Bearer {token}"}

        # Test place search
        try:
            response = await self.client.get(
                f"{self.base_url}/places/search/quick",
                params={"q": "restaurant", "lat": 40.7128,
                        "lng": -74.0060, "radius_km": 10},
                headers=headers
            )
            if response.status_code == 200:
                data = response.json()
                self.log_test("Place Search", True, f"Results: {len(data)}")
            else:
                self.log_test("Place Search", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Place Search", False, f"Error: {str(e)}")

        # Test trending places
        try:
            response = await self.client.get(
                f"{self.base_url}/places/trending",
                params={"lat": 40.7128, "lng": -74.0060, "radius_km": 10},
                headers=headers
            )
            if response.status_code == 200:
                data = response.json()
                self.log_test("Trending Places", True,
                              f"Items: {len(data.get('items', []))}")
            else:
                self.log_test("Trending Places", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Trending Places", False, f"Error: {str(e)}")

    async def test_collections_endpoints(self, token: str):
        """Test collection endpoints"""
        headers = {"Authorization": f"Bearer {token}"}

        # Test creating collection
        try:
            collection_data = {
                "name": "Test Collection",
                "visibility": "public"
            }
            response = await self.client.post(f"{self.base_url}/collections", json=collection_data, headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Create Collection", True,
                              f"Name: {data.get('name', 'N/A')}")
            else:
                self.log_test("Create Collection", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Create Collection", False, f"Error: {str(e)}")

        # Test getting collections
        try:
            response = await self.client.get(f"{self.base_url}/collections", headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Get Collections", True,
                              f"Count: {len(data.get('items', []))}")
            else:
                self.log_test("Get Collections", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Get Collections", False, f"Error: {str(e)}")

    async def test_activity_endpoints(self, token: str):
        """Test activity feed endpoints"""
        headers = {"Authorization": f"Bearer {token}"}

        # Test getting activity feed
        try:
            response = await self.client.get(f"{self.base_url}/activity/feed", headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Get Activity Feed", True,
                              f"Items: {len(data.get('items', []))}")
            else:
                self.log_test("Get Activity Feed", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Get Activity Feed", False, f"Error: {str(e)}")

        # Test getting my activities
        try:
            response = await self.client.get(f"{self.base_url}/activity/my-activities", headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Get My Activities", True,
                              f"Items: {len(data.get('items', []))}")
            else:
                self.log_test("Get My Activities", False,
                              f"Status code: {response.status_code}")
        except Exception as e:
            self.log_test("Get My Activities", False, f"Error: {str(e)}")

    async def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting Circles Application Tests")
        print("=" * 50)

        # Test system endpoints
        await self.test_health_check()
        await self.test_metrics_endpoint()

        # Test authentication
        await self.test_auth_otp_request()
        token = await self.test_auth_otp_verify()

        # Test onboarding
        await self.test_onboarding_phone_otp()
        await self.test_onboarding_phone_verify()
        await self.test_username_availability()
        await self.test_user_setup()

        # Test authenticated endpoints if we have a token
        if token:
            await self.test_authenticated_endpoints(token)
            await self.test_places_endpoints(token)
            await self.test_collections_endpoints(token)
            await self.test_activity_endpoints(token)
        else:
            print("⚠️  Skipping authenticated tests - no token available")

        # Print summary
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)

        passed = sum(1 for result in self.test_results if result["success"])
        total = len(self.test_results)

        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(
            f"Success Rate: {(passed/total)*100:.1f}%" if total > 0 else "0%")

        if total - passed > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['test']}: {result['details']}")

        return passed == total


async def main():
    """Main test runner"""
    async with CirclesTester() as tester:
        success = await tester.run_all_tests()
        return 0 if success else 1


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
