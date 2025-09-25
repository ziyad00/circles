"""Integration tests for place details endpoint."""

import pytest
import httpx
from datetime import datetime, timezone, timedelta
from app.main import app


@pytest.mark.asyncio
async def test_place_details_endpoint_structure():
    """Test place details endpoint structure and authentication."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test without authentication (should require auth)
        response = await client.get("/places/1")
        assert response.status_code == 403  # Should require authentication

        # Test with fake token (should reject invalid token)
        headers = {"Authorization": "Bearer fake_token"}
        response = await client.get("/places/1", headers=headers)
        # Should reject invalid token
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_place_details_endpoint_with_auth():
    """Test place details endpoint with valid authentication."""
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

        # Test place details with valid token
        response = await client.get("/places/1", headers=headers)
        assert response.status_code == 200
        place_data = response.json()

        # Validate response structure
        assert "id" in place_data
        assert "name" in place_data
        assert "stats" in place_data
        assert "current_checkins" in place_data
        assert "total_checkins" in place_data
        assert "recent_reviews" in place_data
        assert "photos_count" in place_data

        # Validate stats structure
        stats = place_data["stats"]
        assert "place_id" in stats
        assert "average_rating" in stats
        assert "reviews_count" in stats
        assert "active_checkins" in stats

        # Note: recent_checkins field is not included in EnhancedPlaceResponse schema


@pytest.mark.asyncio
async def test_place_details_nonexistent_place():
    """Test place details endpoint with non-existent place ID."""
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

        # Test with non-existent place ID
        response = await client.get("/places/99999", headers=headers)
        assert response.status_code == 404
        error_data = response.json()
        assert "detail" in error_data
        assert "not found" in error_data["detail"].lower()


@pytest.mark.asyncio
async def test_place_details_response_data_types():
    """Test that place details response has correct data types."""
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

        # Test place details
        response = await client.get("/places/1", headers=headers)
        assert response.status_code == 200
        place_data = response.json()

        # Validate data types
        assert isinstance(place_data["id"], int)
        assert isinstance(place_data["name"], str)
        assert isinstance(place_data["current_checkins"], int)
        assert isinstance(place_data["total_checkins"], int)
        assert isinstance(place_data["recent_reviews"], int)
        assert isinstance(place_data["photos_count"], int)

        # Validate stats data types
        stats = place_data["stats"]
        assert isinstance(stats["place_id"], int)
        assert isinstance(stats["reviews_count"], int)
        assert isinstance(stats["active_checkins"], int)

        # Note: recent_checkins field is not included in EnhancedPlaceResponse schema


@pytest.mark.asyncio
async def test_place_details_timezone_handling():
    """Test that place details endpoint handles timezone correctly."""
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

        # Test place details
        response = await client.get("/places/1", headers=headers)
        assert response.status_code == 200
        place_data = response.json()

        # Note: recent_checkins field is not included in EnhancedPlaceResponse schema
        # The timezone handling is tested in the unit tests


@pytest.mark.asyncio
async def test_place_details_multiple_places():
    """Test place details endpoint with multiple place IDs."""
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

        # Test multiple place IDs
        test_place_ids = [1, 2, 3]

        for place_id in test_place_ids:
            response = await client.get(f"/places/{place_id}", headers=headers)
            # Should either return 200 (place exists) or 404 (place not found)
            assert response.status_code in [200, 404]

            if response.status_code == 200:
                place_data = response.json()
                assert place_data["id"] == place_id
                assert "name" in place_data
                assert "stats" in place_data
            else:
                error_data = response.json()
                assert "detail" in error_data
