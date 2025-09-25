"""
HTTP Integration tests for Collections and Media endpoints
Tests the actual HTTP API endpoints
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
import asyncio
from app.main import app


class TestCollectionsAndMediaIntegration:
    """Integration tests for collections and media endpoints"""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test that the backend is running"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["app"] == "Circles"

    @pytest.mark.asyncio
    async def test_create_user_and_collection_flow(self):
        """Test complete user creation and collection workflow"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Step 1: Request OTP
            response = await client.post(
                "/onboarding/request-otp",
                json={"phone": "+1234567890"}
            )
            assert response.status_code == 200
            otp_data = response.json()
            assert "otp" in otp_data

            # Step 2: Verify OTP
            response = await client.post(
                "/onboarding/verify-otp",
                json={"phone": "+1234567890", "otp_code": otp_data["otp"]}
            )
            assert response.status_code == 200
            verify_data = response.json()
            assert "access_token" in verify_data
            token = verify_data["access_token"]

            # Step 3: Complete profile setup
            response = await client.post(
                "/onboarding/complete-setup",
                json={
                    "username": "integrationtest",
                    "first_name": "Integration",
                    "last_name": "Test"
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            setup_data = response.json()
            assert setup_data["user"]["username"] == "integrationtest"

            # Step 4: Test collections endpoint (should be empty)
            response = await client.get(
                "/collections/",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            collections = response.json()
            assert collections == []

            # Step 5: Create a collection
            response = await client.post(
                "/collections/",
                json={
                    "name": "Test Collection",
                    "description": "Created during integration test",
                    "is_public": True
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            collection_data = response.json()
            assert collection_data["name"] == "Test Collection"
            assert collection_data["user_id"] == setup_data["user"]["id"]

            # Step 6: Verify collection appears in list
            response = await client.get(
                "/collections/",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            collections = response.json()
            assert len(collections) == 1
            assert collections[0]["name"] == "Test Collection"

            # Step 7: Test legacy collections endpoint
            user_id = setup_data["user"]["id"]
            response = await client.get(
                f"/users/{user_id}/collections",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            legacy_collections = response.json()
            assert len(legacy_collections) == 1
            assert legacy_collections[0]["name"] == "Test Collection"

    @pytest.mark.asyncio
    async def test_user_media_with_checkins(self):
        """Test user media endpoint with check-ins"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Create user
            response = await client.post(
                "/onboarding/request-otp",
                json={"phone": "+1234567891"}
            )
            otp_data = response.json()

            response = await client.post(
                "/onboarding/verify-otp",
                json={"phone": "+1234567891", "otp_code": otp_data["otp"]}
            )
            token = response.json()["access_token"]

            # Complete setup
            response = await client.post(
                "/onboarding/complete-setup",
                json={
                    "username": "mediatest",
                    "first_name": "Media",
                    "last_name": "Test"
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            user_id = response.json()["user"]["id"]

            # Create a check-in (this should work based on earlier testing)
            response = await client.post(
                "/places/check-ins",
                json={
                    "place_id": 1,
                    "comment": "Test check-in for media",
                    "latitude": 24.7876,
                    "longitude": 46.6597
                },
                headers={"Authorization": f"Bearer {token}"}
            )

            # Test user media endpoint
            response = await client.get(
                f"/users/{user_id}/media",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            media_data = response.json()
            assert "items" in media_data
            assert "total" in media_data

    @pytest.mark.asyncio
    async def test_trending_and_nearby_still_work(self):
        """Test that the core Foursquare functionality still works"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Test trending
            response = await client.get(
                "/places/trending?lat=24.787603355754264&lng=46.65968507410644&limit=2"
            )
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert len(data["items"]) > 0

            # Test nearby
            response = await client.get(
                "/places/nearby?lat=24.787603355754264&lng=46.65968507410644&limit=2"
            )
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert len(data["items"]) > 0

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling for invalid requests"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Test 401 for unauthenticated requests
            response = await client.get("/collections/")
            assert response.status_code == 401

            # Test 404 for non-existent user collections
            response = await client.get("/users/999/collections")
            assert response.status_code == 404

            # Test 404 for non-existent user media
            response = await client.get("/users/999/media")
            assert response.status_code == 404


if __name__ == "__main__":
    # Run the integration tests
    test_instance = TestCollectionsAndMediaIntegration()

    async def run_tests():
        await test_instance.test_health_endpoint()
        await test_instance.test_create_user_and_collection_flow()
        await test_instance.test_user_media_with_checkins()
        await test_instance.test_trending_and_nearby_still_work()
        await test_instance.test_error_handling()

        print("✅ All integration tests passed!")

    asyncio.run(run_tests())
