"""Integration tests for user profile endpoints."""

import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_user_profile_endpoints_structure():
    """Test user profile endpoints return correct structure."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test without authentication first (should get 401)
        response = await client.get("/users/1/collections")
        assert response.status_code == 401
        
        response = await client.get("/users/1/check-ins")
        assert response.status_code == 401
        
        response = await client.get("/users/1/media")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_profile_endpoints_with_auth():
    """Test user profile endpoints with authentication."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create test user and get token
        response = await client.post("/onboarding/request-otp", json={"phone": "+1234567890"})
        assert response.status_code == 200
        otp_data = response.json()
        assert "otp" in otp_data
        
        response = await client.post("/onboarding/verify-otp", json={
            "phone": "+1234567890", 
            "otp_code": otp_data["otp"]
        })
        assert response.status_code == 200
        verify_data = response.json()
        token = verify_data["access_token"]
        user_id = verify_data["user"]["id"]
        
        # Test collections endpoint
        response = await client.get(
            f"/users/{user_id}/collections",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        collections = response.json()
        assert isinstance(collections, list)
        
        # Test check-ins endpoint
        response = await client.get(
            f"/users/{user_id}/check-ins",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        checkins = response.json()
        assert isinstance(checkins, list)
        
        # Test media endpoint
        response = await client.get(
            f"/users/{user_id}/media",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        media = response.json()
        assert "items" in media
        assert "total" in media
        assert "limit" in media
        assert "offset" in media
        assert isinstance(media["items"], list)
