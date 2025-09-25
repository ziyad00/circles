"""Integration tests for user search and discovery endpoints."""

import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_user_search_endpoint():
    """Test user search endpoint."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test user search without authentication (should require auth)
        response = await client.get("/users/search?q=test")
        assert response.status_code == 403  # Should require authentication

        # Test with fake token (should reject invalid token)
        headers = {"Authorization": "Bearer fake_token"}
        response = await client.get("/users/search?q=test", headers=headers)
        # Should reject invalid token
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_user_profile_endpoints_for_other_users():
    """Test accessing other users' profiles, collections, and check-ins."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test with fake token (should reject invalid token)
        headers = {"Authorization": "Bearer fake_token"}

        # Test accessing another user's profile
        response = await client.get("/users/1", headers=headers)
        assert response.status_code in [
            401, 403, 404]  # Should reject or not found

        # Test accessing another user's collections
        response = await client.get("/users/1/collections", headers=headers)
        # Should reject invalid token
        assert response.status_code in [401, 403]

        # Test accessing another user's check-ins
        response = await client.get("/users/1/check-ins", headers=headers)
        # Should reject invalid token
        assert response.status_code in [401, 403]

        # Test accessing another user's media
        response = await client.get("/users/1/media", headers=headers)
        # Should reject invalid token
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_places_endpoints_access():
    """Test places endpoints access patterns."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test public places endpoints (should work without auth)
        response = await client.get("/places/trending?lat=24.7876&lng=46.6597&limit=5")
        assert response.status_code == 200

        response = await client.get("/places/nearby?lat=24.7876&lng=46.6597&limit=5")
        assert response.status_code == 200

        # Test place search (should require auth)
        response = await client.get("/places/search?q=restaurant")
        assert response.status_code == 403  # Should require authentication

        # Test place details (should require auth)
        response = await client.get("/places/1")
        assert response.status_code == 403  # Should require authentication

        # Test place details with fake token
        headers = {"Authorization": "Bearer fake_token"}
        response = await client.get("/places/1", headers=headers)
        assert response.status_code in [
            401, 403, 404]  # Should reject or not found


@pytest.mark.asyncio
async def test_collections_endpoints_access():
    """Test collections endpoints access patterns."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test collections endpoints (should require auth)
        response = await client.get("/collections/")
        assert response.status_code == 403  # Should require authentication

        response = await client.get("/collections/1/items")
        assert response.status_code == 403  # Should require authentication

        # Test with fake token
        headers = {"Authorization": "Bearer fake_token"}
        response = await client.get("/collections/", headers=headers)
        # Should reject invalid token
        assert response.status_code in [401, 403]

        response = await client.get("/collections/1/items", headers=headers)
        # Should reject invalid token
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_follow_endpoints_access():
    """Test follow endpoints access patterns."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test follow endpoints (should require auth)
        response = await client.get("/follow/followers")
        assert response.status_code == 403  # Should require authentication

        response = await client.get("/follow/following")
        assert response.status_code == 403  # Should require authentication

        response = await client.get("/follow/1/followers")
        assert response.status_code == 403  # Should require authentication

        # Test with fake token
        headers = {"Authorization": "Bearer fake_token"}
        response = await client.get("/follow/followers", headers=headers)
        # Should reject invalid token
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_dms_endpoints_access():
    """Test direct messages endpoints access patterns."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test DM endpoints (should require auth)
        response = await client.get("/dms/inbox")
        assert response.status_code == 403  # Should require authentication

        # Test with fake token
        headers = {"Authorization": "Bearer fake_token"}
        response = await client.get("/dms/inbox", headers=headers)
        # Should reject invalid token
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_public_vs_private_endpoints():
    """Test which endpoints are public vs private."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Public endpoints (should work without auth)
        public_endpoints = [
            "/health",
            "/places/trending?lat=24.7876&lng=46.6597&limit=5",
            "/places/nearby?lat=24.7876&lng=46.6597&limit=5",
            "/places/lookups/countries",
            "/places/lookups/cities",
            "/places/lookups/neighborhoods",
        ]

        for endpoint in public_endpoints:
            response = await client.get(endpoint)
            assert response.status_code == 200, f"Public endpoint {endpoint} should work without auth"

        # Private endpoints (should require auth)
        private_endpoints = [
            "/users/search?q=test",
            "/users/1",
            "/users/1/collections",
            "/users/1/check-ins",
            "/users/1/media",
            "/places/1",
            "/places/search?q=test",
            "/collections/",
            "/collections/1/items",
            "/follow/followers",
            "/follow/following",
            "/dms/inbox",
            "/auth/me",
        ]

        for endpoint in private_endpoints:
            response = await client.get(endpoint)
            assert response.status_code == 403, f"Private endpoint {endpoint} should require auth"
