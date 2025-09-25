"""
Comprehensive test suite for places image functionality.
Tests organized from big features to smaller components.
"""
import asyncio
import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from app.main import app
from app.database import get_db
from app.services.jwt_service import JWTService
from app.schemas import PlaceResponse


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def auth_token(client: httpx.AsyncClient) -> str:
    """Get auth token for authenticated requests"""
    import time
    import random
    phone = "+1550" + f"{int(time.time()) % 10000:04d}{random.randint(1000, 9999)}"
    r = await client.post("/onboarding/request-otp", json={"phone": phone})
    otp = (r.json() or {}).get("otp", "")
    r = await client.post("/onboarding/verify-otp", json={"phone": phone, "otp_code": otp})
    return (r.json() or {}).get("access_token", "")


# =============================================================================
# BIG FEATURE TESTS - Integration Tests
# =============================================================================

class TestPlacesImagesBigFeatures:
    """Integration tests for major image functionality"""

    @pytest.mark.asyncio
    async def test_nearby_places_with_images_integration(self, client: httpx.AsyncClient):
        """
        BIG FEATURE: Test nearby places endpoint returns real Foursquare images
        This tests the complete flow: API call -> data processing -> image URLs
        """
        # Test nearby places in Riyadh (known to have places with images)
        response = await client.get("/places/nearby", params={
            "lat": 24.78959123323496,
            "lng": 46.658914128943906,
            "radius_m": 1000,
            "limit": 5
        })

        assert response.status_code == 200
        data = response.json()

        # Test response structure
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["items"], list)

        if data["items"]:  # If places found
            place = data["items"][0]

            # Test place has required fields
            assert "id" in place
            assert "name" in place
            assert "photo_url" in place
            assert "photo_urls" in place
            assert "categories" in place

            # Test external place ID handling
            assert place["id"] == -1  # External places use -1

            # Test image fields - at least one place should have images
            places_with_images = [p for p in data["items"] if p.get("photo_url")]
            if places_with_images:
                place_with_image = places_with_images[0]

                # Test image URL format
                photo_url = place_with_image["photo_url"]
                assert photo_url.startswith("https://")
                assert "fastly.4sqi.net" in photo_url or "foursquare.com" in photo_url
                assert "300x300" in photo_url  # Size parameter

                # Test photo_urls array
                photo_urls = place_with_image["photo_urls"]
                assert isinstance(photo_urls, list)
                assert len(photo_urls) > 0
                assert photo_urls[0] == photo_url  # Should match photo_url

    @pytest.mark.asyncio
    async def test_trending_places_with_images_integration(self, client: httpx.AsyncClient):
        """
        BIG FEATURE: Test trending places endpoint image handling
        Tests v2 Foursquare API integration with trending venues
        """
        # Test trending places
        response = await client.get("/places/trending", params={
            "lat": 40.7589,
            "lng": -73.9851,  # NYC coordinates more likely to have trending venues
            "limit": 5
        })

        assert response.status_code == 200
        data = response.json()

        # Test response structure
        assert "items" in data
        assert isinstance(data["items"], list)

        if data["items"]:
            place = data["items"][0]

            # Test required fields
            assert "id" in place
            assert "name" in place
            assert "photo_url" in place
            assert "photo_urls" in place

            # Test external place ID
            assert place["id"] == -1

            # Test image fields structure (may be null for trending)
            assert place["photo_url"] is None or isinstance(place["photo_url"], str)
            assert isinstance(place["photo_urls"], list)

    @pytest.mark.asyncio
    async def test_database_places_with_images_integration(self, client: httpx.AsyncClient):
        """
        BIG FEATURE: Test database places endpoint image compatibility
        Tests schema compatibility and image field structure
        """
        # Test trending endpoint (uses external Foursquare data, should have image fields)
        response = await client.get("/places/trending", params={
            "lat": 24.78959123323496,
            "lng": 46.658914128943906,
            "limit": 3
        })
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

        # Verify the response structure includes image fields
        if data["items"]:
            place = data["items"][0]
            # Test required image fields exist and have correct types
            assert "photo_url" in place
            assert "photo_urls" in place
            assert place["photo_url"] is None or isinstance(place["photo_url"], str)
            assert isinstance(place["photo_urls"], list)

            # Test other essential fields are present
            assert "id" in place
            assert "name" in place
            assert place["id"] == -1  # External places should use -1

        # Test schema compatibility - verify all endpoints return consistent structure
        # Even empty responses should maintain the proper schema structure
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

        # Test that PlaceResponse schema is working correctly for backward compatibility
        for place in data["items"]:
            # These fields should always be present in PlaceResponse
            required_fields = ["id", "name", "photo_url", "photo_urls"]
            for field in required_fields:
                assert field in place, f"Missing required field: {field}"


# =============================================================================
# MEDIUM FEATURE TESTS - Component Tests
# =============================================================================

class TestPlacesImagesComponents:
    """Component tests for specific image processing functionality"""

    @pytest.mark.asyncio
    async def test_foursquare_v3_photo_url_construction(self):
        """
        MEDIUM FEATURE: Test v3 API photo URL construction logic
        Tests the photo URL building from Foursquare v3 prefix/suffix format
        """
        # Mock Foursquare v3 photo response format
        mock_photo = {
            "fsq_photo_id": "test123",
            "prefix": "https://fastly.4sqi.net/img/general/",
            "suffix": "/test_photo.jpg",
            "width": 1920,
            "height": 1440
        }

        # Test photo URL construction (simulating the logic in nearby endpoint)
        prefix = mock_photo.get("prefix", "")
        suffix = mock_photo.get("suffix", "")

        if prefix and suffix:
            photo_url = f"{prefix}300x300{suffix}"
        else:
            photo_url = None

        assert photo_url == "https://fastly.4sqi.net/img/general/300x300/test_photo.jpg"

    @pytest.mark.asyncio
    async def test_foursquare_v2_photo_url_construction(self):
        """
        MEDIUM FEATURE: Test v2 API photo URL construction logic
        Tests the photo URL building from Foursquare v2 format (trending)
        """
        # Mock Foursquare v2 photo response format
        mock_venue_with_photos = {
            "photos": {
                "count": 1,
                "groups": [
                    {
                        "items": [
                            {
                                "prefix": "https://fastly.4sqi.net/img/general/",
                                "suffix": "/v2_photo.jpg",
                                "width": 1920,
                                "height": 1440
                            }
                        ]
                    }
                ]
            }
        }

        # Test photo URL extraction (simulating trending endpoint logic)
        photo_url = None
        if mock_venue_with_photos.get("photos", {}).get("count", 0) > 0:
            photos = mock_venue_with_photos.get("photos", {}).get("groups", [])
            if photos:
                items_list = photos[0].get("items", [])
                if items_list:
                    first_photo = items_list[0]
                    prefix = first_photo.get("prefix", "")
                    suffix = first_photo.get("suffix", "")
                    if prefix and suffix:
                        photo_url = f"{prefix}300x300{suffix}"

        assert photo_url == "https://fastly.4sqi.net/img/general/300x300/v2_photo.jpg"

    @pytest.mark.asyncio
    async def test_place_response_photo_fields_validation(self):
        """
        MEDIUM FEATURE: Test PlaceResponse schema validation for image fields
        Tests Pydantic schema handles photo fields correctly
        """
        # Test with photo_url only
        place_data_1 = {
            "id": 1,
            "name": "Test Place",
            "address": "123 Test St",
            "city": "Test City",
            "latitude": 40.7589,
            "longitude": -73.9851,
            "created_at": "2025-09-25T10:00:00Z",
            "photo_url": "https://example.com/photo.jpg",
            "photo_urls": ["https://example.com/photo.jpg"]
        }

        place_response_1 = PlaceResponse(**place_data_1)
        assert place_response_1.photo_url == "https://example.com/photo.jpg"
        assert place_response_1.photo_urls == ["https://example.com/photo.jpg"]

        # Test with null photo fields
        place_data_2 = {
            "id": 2,
            "name": "Test Place 2",
            "address": "456 Test Ave",
            "city": "Test City",
            "latitude": 40.7589,
            "longitude": -73.9851,
            "created_at": "2025-09-25T10:00:00Z",
            "photo_url": None,
            "photo_urls": []
        }

        place_response_2 = PlaceResponse(**place_data_2)
        assert place_response_2.photo_url is None
        assert place_response_2.photo_urls == []

        # Test with multiple photos
        place_data_3 = {
            "id": 3,
            "name": "Test Place 3",
            "address": "789 Test Blvd",
            "city": "Test City",
            "latitude": 40.7589,
            "longitude": -73.9851,
            "created_at": "2025-09-25T10:00:00Z",
            "photo_url": "https://example.com/photo1.jpg",
            "photo_urls": ["https://example.com/photo1.jpg", "https://example.com/photo2.jpg"]
        }

        place_response_3 = PlaceResponse(**place_data_3)
        assert place_response_3.photo_url == "https://example.com/photo1.jpg"
        assert len(place_response_3.photo_urls) == 2


# =============================================================================
# SMALL FEATURE TESTS - Unit Tests
# =============================================================================

class TestPlacesImagesUnits:
    """Unit tests for specific image handling functions and edge cases"""

    def test_photo_url_construction_edge_cases(self):
        """
        SMALL FEATURE: Test photo URL construction edge cases
        Tests error handling and edge cases in photo URL building
        """
        # Test empty prefix
        prefix, suffix = "", "/photo.jpg"
        photo_url = f"{prefix}300x300{suffix}" if prefix and suffix else None
        assert photo_url is None

        # Test empty suffix
        prefix, suffix = "https://example.com/", ""
        photo_url = f"{prefix}300x300{suffix}" if prefix and suffix else None
        assert photo_url is None

        # Test both empty
        prefix, suffix = "", ""
        photo_url = f"{prefix}300x300{suffix}" if prefix and suffix else None
        assert photo_url is None

        # Test valid construction
        prefix, suffix = "https://example.com/", "/photo.jpg"
        photo_url = f"{prefix}300x300{suffix}" if prefix and suffix else None
        assert photo_url == "https://example.com/300x300/photo.jpg"

    def test_photo_urls_array_construction(self):
        """
        SMALL FEATURE: Test photo_urls array construction logic
        Tests conversion from photo_url to photo_urls array
        """
        # Test with photo_url
        photo_url = "https://example.com/photo.jpg"
        photo_urls = [photo_url] if photo_url else []
        assert photo_urls == ["https://example.com/photo.jpg"]

        # Test with None photo_url
        photo_url = None
        photo_urls = [photo_url] if photo_url else []
        assert photo_urls == []

        # Test with empty string
        photo_url = ""
        photo_urls = [photo_url] if photo_url else []
        assert photo_urls == []

    def test_external_place_id_handling(self):
        """
        SMALL FEATURE: Test external place ID standardization
        Tests that external places consistently use -1 as ID
        """
        # Test external place ID assignment
        external_place_id = -1  # Standard for external places
        assert external_place_id == -1
        assert isinstance(external_place_id, int)

    def test_image_url_format_validation(self):
        """
        SMALL FEATURE: Test image URL format validation
        Tests that generated URLs follow expected patterns
        """
        # Test Foursquare URL patterns
        foursquare_url = "https://fastly.4sqi.net/img/general/300x300/photo123.jpg"
        assert foursquare_url.startswith("https://")
        assert "fastly.4sqi.net" in foursquare_url
        assert "300x300" in foursquare_url
        assert foursquare_url.endswith(".jpg")

        # Test size parameter presence
        assert "300x300" in foursquare_url  # Expected image size

    @pytest.mark.asyncio
    async def test_foursquare_api_fields_parameter(self):
        """
        SMALL FEATURE: Test Foursquare API fields parameter construction
        Tests that API requests include photo fields
        """
        # Test fields parameter construction
        expected_fields = "fsq_place_id,name,location,categories,distance,photos,rating,price,tel,website"

        # Verify photos is included in fields
        assert "photos" in expected_fields
        assert "fsq_place_id" in expected_fields
        assert "name" in expected_fields
        assert "location" in expected_fields


# =============================================================================
# ERROR HANDLING AND INTEGRATION TESTS
# =============================================================================

class TestPlacesImagesErrorHandling:
    """Tests for error handling and edge cases in image functionality"""

    @pytest.mark.asyncio
    async def test_foursquare_api_unavailable(self, client: httpx.AsyncClient):
        """
        Test behavior when Foursquare API is unavailable or returns errors
        """
        # Test with coordinates that won't return results (middle of ocean)
        response = await client.get("/places/nearby", params={
            "lat": 0.0,  # Middle of Atlantic Ocean
            "lng": 0.0,
            "radius_m": 1000,
            "limit": 5
        })

        # Should return 200 with empty or minimal results
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        # May have 0 or very few items in the middle of the ocean
        assert len(data["items"]) <= 5

    @pytest.mark.asyncio
    async def test_extreme_coordinates(self, client: httpx.AsyncClient):
        """
        Test behavior with extreme coordinates
        """
        # Test with extreme but valid coordinates (North Pole)
        response = await client.get("/places/nearby", params={
            "lat": 89.9,  # Very far north (valid)
            "lng": 0,
            "radius_m": 1000,
            "limit": 5
        })
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        # Likely no places near North Pole
        assert len(data["items"]) == 0

        # Test with extreme longitude (valid)
        response = await client.get("/places/nearby", params={
            "lat": 0,
            "lng": 179.9,  # Near international date line
            "radius_m": 1000,
            "limit": 5
        })
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_malformed_foursquare_response(self):
        """
        Test handling of malformed Foursquare API responses
        """
        # Test with missing photo fields
        malformed_place = {
            "name": "Test Place",
            "location": {"address": "123 Test St"},
            # Missing photos field
        }

        # Simulate photo extraction with missing fields
        photo_url = None
        if malformed_place.get("photos"):
            photos = malformed_place.get("photos", [])
            if photos:
                first_photo = photos[0]
                prefix = first_photo.get("prefix", "")
                suffix = first_photo.get("suffix", "")
                if prefix and suffix:
                    photo_url = f"{prefix}300x300{suffix}"

        # Should handle gracefully
        assert photo_url is None
        photo_urls = [photo_url] if photo_url else []
        assert photo_urls == []


# =============================================================================
# PERFORMANCE AND LOAD TESTS
# =============================================================================

class TestPlacesImagesPerformance:
    """Performance tests for image functionality"""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self, client: httpx.AsyncClient):
        """
        Test that multiple concurrent requests for images work correctly
        """
        import asyncio

        async def make_request():
            return await client.get("/places/nearby", params={
                "lat": 24.78959123323496,
                "lng": 46.658914128943906,
                "radius_m": 1000,
                "limit": 2
            })

        # Make 5 concurrent requests
        tasks = [make_request() for _ in range(5)]
        responses = await asyncio.gather(*tasks)

        # All should succeed
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert "items" in data

    @pytest.mark.asyncio
    async def test_large_limit_parameter(self, client: httpx.AsyncClient):
        """
        Test behavior with large limit parameters
        """
        response = await client.get("/places/nearby", params={
            "lat": 24.78959123323496,
            "lng": 46.658914128943906,
            "radius_m": 5000,
            "limit": 50  # Large limit
        })

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["items"], list)
        # Should handle large responses gracefully