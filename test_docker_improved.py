#!/usr/bin/env python3
"""
Improved test script that handles OTP verification properly
"""

import asyncio
import httpx
import json
import sys
import re
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


async def test_otp_flow(client):
    """Test OTP request and verification flow"""
    print("🔐 Testing OTP Authentication Flow")
    
    # Step 1: Request OTP
    response = await client.post("/auth/request-otp", json={"email": "test@example.com"})
    if response.status_code != 200:
        return False, f"❌ OTP Request failed: {response.status_code}"
    
    # Extract OTP from response (development mode)
    data = response.json()
    message = data.get("message", "")
    otp_match = re.search(r'(\d{6})', message)
    if not otp_match:
        return False, "❌ Could not extract OTP from response"
    
    otp_code = otp_match.group(1)
    print(f"   📧 OTP extracted: {otp_code}")
    
    # Step 2: Verify OTP
    verify_response = await client.post("/auth/verify-otp", json={
        "email": "test@example.com",
        "otp_code": otp_code
    })
    
    if verify_response.status_code == 200:
        return True, "✅ OTP Authentication Flow - Success"
    else:
        return False, f"❌ OTP Verification failed: {verify_response.status_code}"


async def test_phone_otp_flow(client):
    """Test phone OTP request and verification flow"""
    print("📱 Testing Phone OTP Authentication Flow")
    
    # Step 1: Request phone OTP (use different phone to avoid rate limiting)
    response = await client.post("/onboarding/request-otp", json={"phone": "+1987654321"})
    if response.status_code != 200:
        return False, f"❌ Phone OTP Request failed: {response.status_code}"
    
    # Extract OTP from response (development mode)
    data = response.json()
    otp_code = data.get("otp", "123456")  # Default to 123456 for testing
    print(f"   📱 Phone OTP extracted: {otp_code}")
    
    # Step 2: Verify phone OTP
    verify_response = await client.post("/onboarding/verify-otp", json={
        "phone": "+1987654321",
        "otp_code": otp_code
    })
    
    if verify_response.status_code == 200:
        return True, "✅ Phone OTP Authentication Flow - Success"
    else:
        return False, f"❌ Phone OTP Verification failed: {verify_response.status_code}"


async def test_user_setup_flow(client):
    """Test user setup flow with authentication"""
    print("👤 Testing User Setup Flow")
    
    # Step 1: Get a valid token by completing phone OTP flow
    phone_response = await client.post("/onboarding/request-otp", json={"phone": "+1555123456"})
    if phone_response.status_code != 200:
        return False, "❌ Phone OTP request failed for setup"
    
    data = phone_response.json()
    otp_code = data.get("otp", "123456")
    
    verify_response = await client.post("/onboarding/verify-otp", json={
        "phone": "+1555123456",
        "otp_code": otp_code
    })
    
    if verify_response.status_code != 200:
        return False, "❌ Phone OTP verification failed for setup"
    
    # Extract token
    verify_data = verify_response.json()
    token = verify_data.get("access_token")
    if not token:
        return False, "❌ No access token received"
    
    print(f"   🔑 Token obtained: {token[:20]}...")
    
    # Step 2: Complete user setup with token
    headers = {"Authorization": f"Bearer {token}"}
    setup_response = await client.post("/onboarding/complete-setup", json={
        "username": "testuser123",
        "first_name": "Test",
        "last_name": "User",
        "interests": ["food", "travel"]
    }, headers=headers)
    
    if setup_response.status_code == 200:
        return True, "✅ User Setup Flow - Success"
    else:
        return False, f"❌ User Setup failed: {setup_response.status_code}"


async def run_tests():
    """Run all tests"""
    print("🚀 Starting Circles Application Tests")
    print("=" * 50)
    print(f"Time: {datetime.now()}")
    print()

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        results = []
        
        # Basic system tests
        print("🔧 Testing System Endpoints")
        basic_tests = [
            ("GET", "/health", None, 200),
            ("GET", "/metrics", None, 200),
        ]
        
        for method, url, data, expected_status in basic_tests:
            success, message = await test_endpoint(client, method, url, data, expected_status)
            print(f"   {message}")
            results.append(success)
        
        print()
        
        # OTP authentication flow
        success, message = await test_otp_flow(client)
        print(f"   {message}")
        results.append(success)
        
        print()
        
        # Phone OTP authentication flow
        success, message = await test_phone_otp_flow(client)
        print(f"   {message}")
        results.append(success)
        
        print()
        
        # Username availability
        success, message = await test_endpoint(client, "POST", "/onboarding/check-username", {"username": "testuser123"}, 200)
        print(f"   {message}")
        results.append(success)
        
        print()
        
        # User setup flow
        success, message = await test_user_setup_flow(client)
        print(f"   {message}")
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
        print(f"Success Rate: {(passed/total)*100:.1f}%" if total > 0 else "0%")

        return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
