"""Detailed integration tests for collections endpoints."""

import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_collections_endpoint_detailed():
    """Test collections endpoint with detailed validation."""
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

        # Test collections endpoint
        response = await client.get("/collections/", headers=headers)
        assert response.status_code == 200
        collections_data = response.json()

        # Validate response structure
        assert isinstance(collections_data, list)

        for collection in collections_data:
            required_fields = [
                "id", "user_id", "name", "description", "is_public",
                "visibility", "created_at"
            ]

            for field in required_fields:
                assert field in collection, f"Missing required field: {field}"

            # Validate data types
            assert isinstance(collection["id"], int)
            assert isinstance(collection["user_id"], int)
            assert isinstance(collection["name"], str)
            assert isinstance(collection["is_public"], bool)
            assert isinstance(collection["visibility"], str)

            # Validate enum values
            valid_visibilities = ["public", "followers", "private"]
            assert collection["visibility"] in valid_visibilities

            # Validate datetime format
            if "created_at" in collection:
                created_at_str = collection["created_at"]
                try:
                    from datetime import datetime
                    datetime.fromisoformat(
                        created_at_str.replace('Z', '+00:00'))
                except ValueError:
                    pytest.fail(f"Invalid datetime format: {created_at_str}")


@pytest.mark.asyncio
async def test_collections_items_endpoint_detailed():
    """Test collections items endpoint with detailed validation."""
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

        # First get collections to find a valid collection ID
        response = await client.get("/collections/", headers=headers)
        assert response.status_code == 200
        collections_data = response.json()

        if not collections_data:
            pytest.skip("No collections available for testing")

        collection_id = collections_data[0]["id"]

        # Test collections items endpoint
        response = await client.get(f"/collections/{collection_id}/items", headers=headers)
        assert response.status_code == 200
        items_data = response.json()

        # Validate response structure
        required_fields = ["items", "total", "limit", "offset"]

        for field in required_fields:
            assert field in items_data, f"Missing required field: {field}"

        # Validate data types
        assert isinstance(items_data["items"], list)
        assert isinstance(items_data["total"], int)
        assert isinstance(items_data["limit"], int)
        assert isinstance(items_data["offset"], int)

        # Validate items structure
        for item in items_data["items"]:
            required_item_fields = [
                "id", "name", "address", "latitude", "longitude",
                "categories", "rating", "created_at"
            ]

            for field in required_item_fields:
                assert field in item, f"Missing required item field: {field}"

            # Validate data types
            assert isinstance(item["id"], int)
            assert isinstance(item["name"], str)
            assert isinstance(item["latitude"], (float, type(None)))
            assert isinstance(item["longitude"], (float, type(None)))
            assert isinstance(item["rating"], (float, type(None)))


@pytest.mark.asyncio
async def test_collections_create_endpoint_detailed():
    """Test collections create endpoint with detailed validation."""
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

        # Test collections create endpoint
        collection_data = {
            "name": "Test Collection",
            "description": "A test collection for testing",
            "is_public": True
        }

        response = await client.post("/collections/", json=collection_data, headers=headers)
        assert response.status_code == 200
        created_collection = response.json()

        # Validate response structure
        required_fields = [
            "id", "user_id", "name", "description", "is_public",
            "visibility", "created_at"
        ]

        for field in required_fields:
            assert field in created_collection, f"Missing required field: {field}"

        # Validate data matches input
        assert created_collection["name"] == collection_data["name"]
        assert created_collection["description"] == collection_data["description"]
        assert created_collection["is_public"] == collection_data["is_public"]

        # Validate data types
        assert isinstance(created_collection["id"], int)
        assert isinstance(created_collection["user_id"], int)
        assert isinstance(created_collection["name"], str)
        assert isinstance(created_collection["description"], str)
        assert isinstance(created_collection["is_public"], bool)
        assert isinstance(created_collection["visibility"], str)


@pytest.mark.asyncio
async def test_collections_nonexistent_collection():
    """Test collections items endpoint with non-existent collection ID."""
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

        # Test with non-existent collection ID
        response = await client.get("/collections/99999/items", headers=headers)
        assert response.status_code == 404
        error_data = response.json()
        assert "detail" in error_data
        assert "not found" in error_data["detail"].lower()


@pytest.mark.asyncio
async def test_collections_authentication_required():
    """Test that collections endpoints require authentication."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test without authentication
        response = await client.get("/collections/")
        assert response.status_code == 403

        response = await client.get("/collections/1/items")
        assert response.status_code == 403

        response = await client.post("/collections/", json={"name": "Test"})
        assert response.status_code == 403

        # Test with fake token
        headers = {"Authorization": "Bearer fake_token"}
        response = await client.get("/collections/", headers=headers)
        assert response.status_code in [401, 403]

        response = await client.get("/collections/1/items", headers=headers)
        assert response.status_code in [401, 403]

        response = await client.post("/collections/", json={"name": "Test"}, headers=headers)
        assert response.status_code in [401, 403]
