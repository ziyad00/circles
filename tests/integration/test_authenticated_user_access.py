"""Integration tests for authenticated access to other users' data."""

import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_authenticated_user_search():
    """Test user search with valid authentication."""
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

        # Test user search with valid token
        response = await client.get("/users/search?q=test", headers=headers)
        assert response.status_code == 200
        search_results = response.json()
        assert isinstance(search_results, list)


@pytest.mark.asyncio
async def test_authenticated_access_to_other_users():
    """Test accessing other users' data with valid authentication."""
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

        # Test accessing another user's profile (should work if user exists and is public)
        response = await client.get("/users/1", headers=headers)
        # Could be 200 (user found and public), 403 (private), or 404 (not found)
        assert response.status_code in [200, 403, 404]

        # Test accessing another user's collections
        response = await client.get("/users/1/collections", headers=headers)
        # Could be 200 (collections found), 403 (private), or 404 (user not found)
        assert response.status_code in [200, 403, 404]

        # Test accessing another user's check-ins
        response = await client.get("/users/1/check-ins", headers=headers)
        # Could be 200 (check-ins found), 403 (private), or 404 (user not found)
        assert response.status_code in [200, 403, 404]

        # Test accessing another user's media
        response = await client.get("/users/1/media", headers=headers)
        # Could be 200 (media found), 403 (private), or 404 (user not found)
        assert response.status_code in [200, 403, 404]


@pytest.mark.asyncio
async def test_authenticated_places_access():
    """Test places endpoints with valid authentication."""
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
        # Could be 200 (place found), 403 (private), or 404 (not found)
        assert response.status_code in [200, 403, 404]

        # Test place search with valid token (should work the same as without auth)
        response = await client.get("/places/search?q=restaurant", headers=headers)
        assert response.status_code == 200

        # Test trending with valid token (should work the same as without auth)
        response = await client.get("/places/trending?lat=24.7876&lng=46.6597&limit=5", headers=headers)
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_authenticated_collections_access():
    """Test collections endpoints with valid authentication."""
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

        # Test user's own collections
        response = await client.get("/collections/", headers=headers)
        assert response.status_code == 200
        collections = response.json()
        assert isinstance(collections, list)

        # Test accessing a specific collection's items
        if collections:
            collection_id = collections[0]["id"]
            response = await client.get(f"/collections/{collection_id}/items", headers=headers)
            assert response.status_code == 200
            items = response.json()
            assert "items" in items
            assert "total" in items
            assert "limit" in items
            assert "offset" in items


@pytest.mark.asyncio
async def test_authenticated_follow_access():
    """Test follow endpoints with valid authentication."""
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

        # Test user's own followers
        response = await client.get("/follow/followers", headers=headers)
        assert response.status_code == 200
        followers = response.json()
        assert isinstance(followers, list)

        # Test user's own following
        response = await client.get("/follow/following", headers=headers)
        assert response.status_code == 200
        following = response.json()
        assert isinstance(following, list)

        # Test another user's followers
        response = await client.get("/follow/1/followers", headers=headers)
        # Could be 200 (followers found), 403 (private), or 404 (user not found)
        assert response.status_code in [200, 403, 404]

        # Test another user's following
        response = await client.get("/follow/1/following", headers=headers)
        # Could be 200 (following found), 403 (private), or 404 (user not found)
        assert response.status_code in [200, 403, 404]


@pytest.mark.asyncio
async def test_authenticated_dms_access():
    """Test DM endpoints with valid authentication."""
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

        # Test user's own DM inbox
        response = await client.get("/dms/inbox", headers=headers)
        assert response.status_code == 200
        inbox = response.json()
        assert isinstance(inbox, list)
