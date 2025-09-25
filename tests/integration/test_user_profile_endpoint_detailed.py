"""Detailed integration tests for user profile endpoint."""

import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_user_profile_endpoint_detailed():
    """Test user profile endpoint with detailed validation."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Get authentication token
        response = await client.post(
            "/onboarding/request-otp",
            json={"phone": "+1234567890"}
        )
        assert response.status_code == 200
        otp_data = response.json()

        if "otp" not in otp_data:
            pytest.skip("OTP not available in test environment")

        response = await client.post(
            "/onboarding/verify-otp",
            json={"phone": "+1234567890", "otp_code": otp_data["otp"]}
        )
        assert response.status_code == 200
        verify_data = response.json()

        if "access_token" not in verify_data:
            pytest.skip("Access token not available in test environment")

        token = verify_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Test user profile
        response = await client.get("/users/2", headers=headers)
        assert response.status_code == 200
        user_data = response.json()

        # Validate response structure
        required_fields = [
            "id", "name", "username", "bio", "avatar_url",
            "availability_status", "availability_mode", "created_at",
            "followers_count", "following_count", "check_ins_count",
            "is_followed", "is_blocked"
        ]

        for field in required_fields:
            assert field in user_data, f"Missing required field: {field}"

        # Validate data types
        assert isinstance(user_data["id"], int)
        assert isinstance(user_data["followers_count"], int)
        assert isinstance(user_data["following_count"], int)
        assert isinstance(user_data["check_ins_count"], int)
        assert isinstance(user_data["is_followed"], bool)
        assert isinstance(user_data["is_blocked"], bool)

        # Validate enum values
        valid_availability_statuses = [
            "available", "busy", "away", "not_available"]
        assert user_data["availability_status"] in valid_availability_statuses

        valid_availability_modes = ["auto", "manual"]
        assert user_data["availability_mode"] in valid_availability_modes


@pytest.mark.asyncio
async def test_user_profile_nonexistent_user():
    """Test user profile endpoint with non-existent user ID."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Get authentication token
        response = await client.post(
            "/onboarding/request-otp",
            json={"phone": "+1234567890"}
        )
        assert response.status_code == 200
        otp_data = response.json()

        if "otp" not in otp_data:
            pytest.skip("OTP not available in test environment")

        response = await client.post(
            "/onboarding/verify-otp",
            json={"phone": "+1234567890", "otp_code": otp_data["otp"]}
        )
        assert response.status_code == 200
        verify_data = response.json()

        if "access_token" not in verify_data:
            pytest.skip("Access token not available in test environment")

        token = verify_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Test with non-existent user ID
        response = await client.get("/users/99999", headers=headers)
        assert response.status_code == 404
        error_data = response.json()
        assert "detail" in error_data
        assert "not found" in error_data["detail"].lower()


@pytest.mark.asyncio
async def test_user_profile_follow_relationship():
    """Test user profile endpoint follow relationship logic."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Get authentication token
        response = await client.post(
            "/onboarding/request-otp",
            json={"phone": "+1234567890"}
        )
        assert response.status_code == 200
        otp_data = response.json()

        if "otp" not in otp_data:
            pytest.skip("OTP not available in test environment")

        response = await client.post(
            "/onboarding/verify-otp",
            json={"phone": "+1234567890", "otp_code": otp_data["otp"]}
        )
        assert response.status_code == 200
        verify_data = response.json()

        if "access_token" not in verify_data:
            pytest.skip("Access token not available in test environment")

        token = verify_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Test user profile
        response = await client.get("/users/2", headers=headers)
        assert response.status_code == 200
        user_data = response.json()

        # Validate follow relationship
        assert "is_followed" in user_data
        assert isinstance(user_data["is_followed"], bool)

        # For now, should be False since we're not following ourselves
        # (This test assumes user ID 2 is the same as the authenticated user)
        # In a real scenario, this would test following other users


@pytest.mark.asyncio
async def test_user_profile_datetime_handling():
    """Test user profile endpoint datetime handling."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Get authentication token
        response = await client.post(
            "/onboarding/request-otp",
            json={"phone": "+1234567890"}
        )
        assert response.status_code == 200
        otp_data = response.json()

        if "otp" not in otp_data:
            pytest.skip("OTP not available in test environment")

        response = await client.post(
            "/onboarding/verify-otp",
            json={"phone": "+1234567890", "otp_code": otp_data["otp"]}
        )
        assert response.status_code == 200
        verify_data = response.json()

        if "access_token" not in verify_data:
            pytest.skip("Access token not available in test environment")

        token = verify_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Test user profile
        response = await client.get("/users/2", headers=headers)
        assert response.status_code == 200
        user_data = response.json()

        # Validate datetime format
        if "created_at" in user_data:
            created_at_str = user_data["created_at"]
            try:
                from datetime import datetime
                datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            except ValueError:
                pytest.fail(f"Invalid datetime format: {created_at_str}")


@pytest.mark.asyncio
async def test_user_profile_consistency():
    """Test user profile endpoint consistency with /auth/me."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Get authentication token
        response = await client.post(
            "/onboarding/request-otp",
            json={"phone": "+1234567890"}
        )
        assert response.status_code == 200
        otp_data = response.json()

        if "otp" not in otp_data:
            pytest.skip("OTP not available in test environment")

        response = await client.post(
            "/onboarding/verify-otp",
            json={"phone": "+1234567890", "otp_code": otp_data["otp"]}
        )
        assert response.status_code == 200
        verify_data = response.json()

        if "access_token" not in verify_data:
            pytest.skip("Access token not available in test environment")

        token = verify_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Get /auth/me data
        response = await client.get("/auth/me", headers=headers)
        assert response.status_code == 200
        me_data = response.json()

        # Get user profile data
        user_id = me_data["id"]
        response = await client.get(f"/users/{user_id}", headers=headers)
        assert response.status_code == 200
        user_data = response.json()

        # Validate consistency
        assert user_data["id"] == me_data["id"]
        assert user_data["username"] == me_data["username"]
        # Note: Some fields might be different due to privacy settings
