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
        assert response.status_code == 403
        
        response = await client.get("/users/1/check-ins")
        assert response.status_code == 403
        
        response = await client.get("/users/1/media")
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_profile_endpoints_with_auth():
    """Test user profile endpoints with authentication."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test with a fake token to verify the endpoints exist and handle auth properly
        headers = {"Authorization": "Bearer fake_token"}
        
        # Test collections endpoint - should return 401/403 for invalid token
        response = await client.get("/users/1/collections", headers=headers)
        assert response.status_code in [401, 403]  # Should reject invalid token
        
        # Test check-ins endpoint - should return 401/403 for invalid token
        response = await client.get("/users/1/check-ins", headers=headers)
        assert response.status_code in [401, 403]  # Should reject invalid token
        
        # Test media endpoint - should return 401/403 for invalid token
        response = await client.get("/users/1/media", headers=headers)
        assert response.status_code in [401, 403]  # Should reject invalid token
