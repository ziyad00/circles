"""Integration tests for discovering users, places, and collections."""

import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_user_discovery_flow():
    """Test the complete user discovery flow."""
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

        # Step 1: Search for users
        response = await client.get("/users/search?q=test", headers=headers)
        assert response.status_code == 200
        users = response.json()
        assert isinstance(users, list)

        # Step 2: For each found user, try to access their profile
        for user in users[:3]:  # Test first 3 users
            user_id = user.get("id")
            if user_id:
                # Test user profile
                response = await client.get(f"/users/{user_id}", headers=headers)
                assert response.status_code in [200, 403, 404]

                # Test user collections
                response = await client.get(f"/users/{user_id}/collections", headers=headers)
                assert response.status_code in [200, 403, 404]

                # Test user check-ins
                response = await client.get(f"/users/{user_id}/check-ins", headers=headers)
                assert response.status_code in [200, 403, 404]

                # Test user media
                response = await client.get(f"/users/{user_id}/media", headers=headers)
                assert response.status_code in [200, 403, 404]


@pytest.mark.asyncio
async def test_places_discovery_flow():
    """Test the complete places discovery flow."""
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

        # Step 1: Search for places
        response = await client.get("/places/search?q=restaurant", headers=headers)
        assert response.status_code == 200
        places = response.json()
        assert "items" in places
        assert isinstance(places["items"], list)

        # Step 2: Get trending places
        response = await client.get("/places/trending?lat=24.7876&lng=46.6597&limit=10", headers=headers)
        assert response.status_code == 200
        trending = response.json()
        assert "items" in trending
        assert isinstance(trending["items"], list)

        # Step 3: Get nearby places
        response = await client.get("/places/nearby?lat=24.7876&lng=46.6597&limit=10", headers=headers)
        assert response.status_code == 200
        nearby = response.json()
        assert "items" in nearby
        assert isinstance(nearby["items"], list)

        # Step 4: For each found place, try to get details
        all_places = []
        if places["items"]:
            all_places.extend(places["items"][:3])  # First 3 from search
        if trending["items"]:
            all_places.extend(trending["items"][:3])  # First 3 from trending
        if nearby["items"]:
            all_places.extend(nearby["items"][:3])  # First 3 from nearby

        for place in all_places[:5]:  # Test first 5 unique places
            place_id = place.get("id")
            if place_id and place_id != -1:  # Skip external places
                response = await client.get(f"/places/{place_id}", headers=headers)
                assert response.status_code in [200, 403, 404]


@pytest.mark.asyncio
async def test_collections_discovery_flow():
    """Test the complete collections discovery flow."""
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

        # Step 1: Get user's own collections
        response = await client.get("/collections/", headers=headers)
        assert response.status_code == 200
        own_collections = response.json()
        assert isinstance(own_collections, list)

        # Step 2: For each collection, get its items
        for collection in own_collections[:3]:  # Test first 3 collections
            collection_id = collection["id"]
            response = await client.get(f"/collections/{collection_id}/items", headers=headers)
            assert response.status_code == 200
            items = response.json()
            assert "items" in items
            assert "total" in items
            assert "limit" in items
            assert "offset" in items

        # Step 3: Search for users and try to access their collections
        response = await client.get("/users/search?q=test", headers=headers)
        assert response.status_code == 200
        users = response.json()

        for user in users[:2]:  # Test first 2 users
            user_id = user.get("id")
            if user_id:
                response = await client.get(f"/users/{user_id}/collections", headers=headers)
                assert response.status_code in [200, 403, 404]

                # If collections are accessible, test accessing their items
                if response.status_code == 200:
                    collections = response.json()
                    # Test first 2 collections
                    for collection in collections[:2]:
                        collection_id = collection["id"]
                        response = await client.get(f"/collections/{collection_id}/items", headers=headers)
                        assert response.status_code in [200, 403, 404]


@pytest.mark.asyncio
async def test_cross_user_data_access():
    """Test accessing data across different users."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Get authentication token for user 1
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

        # Test accessing different user IDs
        test_user_ids = [1, 2, 3, 999]  # Include a non-existent user ID

        for user_id in test_user_ids:
            # Test user profile
            response = await client.get(f"/users/{user_id}", headers=headers)
            assert response.status_code in [200, 403, 404]

            # Test user collections
            response = await client.get(f"/users/{user_id}/collections", headers=headers)
            assert response.status_code in [200, 403, 404]

            # Test user check-ins
            response = await client.get(f"/users/{user_id}/check-ins", headers=headers)
            assert response.status_code in [200, 403, 404]

            # Test user media
            response = await client.get(f"/users/{user_id}/media", headers=headers)
            assert response.status_code in [200, 403, 404]

            # Test user's followers
            response = await client.get(f"/follow/{user_id}/followers", headers=headers)
            assert response.status_code in [200, 403, 404]

            # Test user's following
            response = await client.get(f"/follow/{user_id}/following", headers=headers)
            assert response.status_code in [200, 403, 404]


@pytest.mark.asyncio
async def test_data_consistency_across_endpoints():
    """Test that data is consistent across different endpoints."""
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

        # Test that user's own data is consistent
        response = await client.get("/auth/me", headers=headers)
        assert response.status_code == 200
        me_data = response.json()
        user_id = me_data.get("id")

        if user_id:
            # Test that /users/{user_id} returns the same user data
            response = await client.get(f"/users/{user_id}", headers=headers)
            if response.status_code == 200:
                user_data = response.json()
                assert user_data["id"] == user_id
                assert user_data["phone"] == me_data["phone"]

            # Test that user's collections are accessible
            response = await client.get(f"/users/{user_id}/collections", headers=headers)
            assert response.status_code == 200
            user_collections = response.json()

            # Test that /collections/ returns the same collections
            response = await client.get("/collections/", headers=headers)
            assert response.status_code == 200
            own_collections = response.json()

            # Collections should be the same
            assert len(user_collections) == len(own_collections)
            for i, collection in enumerate(user_collections):
                assert collection["id"] == own_collections[i]["id"]
                assert collection["name"] == own_collections[i]["name"]
