#!/usr/bin/env python3
"""
Simple test script to run inside Docker container
"""

import asyncio
import httpx
import json
import sys
from datetime import datetime


async def test_endpoint(client, method, url, data=None, expected_status=200):
    """Test a single endpoint"""
    try:
        if method == "GET":
            response = await client.get(url)
        elif method == "POST":
            response = await client.post(url, json=data)
        elif method == "PUT":
            response = await client.put(url, json=data)
        else:
            return False, f"Unknown method: {method}"

        if response.status_code == expected_status:
            return True, f"✅ {method} {url} - Status: {response.status_code}"
        else:
            return False, f"❌ {method} {url} - Expected {expected_status}, got {response.status_code}"
    except Exception as e:
        return False, f"❌ {method} {url} - Error: {str(e)}"


async def run_tests():
    """Run all tests"""
    print("🚀 Starting Circles Application Tests")
    print("=" * 50)
    print(f"Time: {datetime.now()}")
    print()

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        tests = [
            # System endpoints
            ("GET", "/health", None, 200),
            ("GET", "/metrics", None, 200),

            # Authentication
            ("POST", "/auth/request-otp", {"email": "test@example.com"}, 200),
            ("POST", "/auth/verify-otp",
             {"email": "test@example.com", "otp_code": "123456"}, 200),

            # Onboarding
            ("POST", "/onboarding/request-otp",
             {"phone": "+1234567890"}, 200),
            ("POST", "/onboarding/verify-otp",
             {"phone": "+1234567890", "otp_code": "123456"}, 200),
            ("POST", "/onboarding/check-username",
             {"username": "testuser123"}, 200),

            # User setup
            ("POST", "/onboarding/complete-setup", {
                "username": "testuser123",
                "first_name": "Test",
                "last_name": "User",
                "interests": ["food", "travel"]
            }, 200),
        ]

        results = []
        for method, url, data, expected_status in tests:
            success, message = await test_endpoint(client, method, url, data, expected_status)
            print(message)
            results.append(success)

        # Print summary
        print()
        print("=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)

        passed = sum(results)
        total = len(results)

        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(
            f"Success Rate: {(passed/total)*100:.1f}%" if total > 0 else "0%")

        return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
