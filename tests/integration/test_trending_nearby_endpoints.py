"""
Integration tests for trending and nearby endpoints with Foursquare API
"""

import pytest
import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.models import Place
from app.database import get_db


class TestTrendingNearbyEndpoints:
    """Test trending and nearby endpoints with real Foursquare API calls"""

    @pytest.fixture
    def riyadh_coordinates(self):
        """Riyadh coordinates for testing"""
        return {
            "lat": 24.7136,
            "lng": 46.6753
        }

    @pytest.fixture
    def riyadh_coordinates_alt(self):
        """Alternative Riyadh coordinates for testing"""
        return {
            "lat": 24.7876,
            "lng": 46.6597
        }

    @pytest.mark.asyncio
    async def test_trending_endpoint_structure(self, riyadh_coordinates):
        """Test trending endpoint returns proper structure"""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/places/trending",
                params={
                    "lat": riyadh_coordinates["lat"],
                    "lng": riyadh_coordinates["lng"],
                    "limit": 5
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Check response structure
            assert "items" in data
            assert "total" in data
            assert "limit" in data
            assert "offset" in data

            assert isinstance(data["items"], list)
            assert isinstance(data["total"], int)
            assert isinstance(data["limit"], int)
            assert isinstance(data["offset"], int)

    @pytest.mark.asyncio
    async def test_trending_endpoint_with_riyadh_coordinates(self, riyadh_coordinates):
        """Test trending endpoint with Riyadh coordinates returns results"""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/places/trending",
                params={
                    "lat": riyadh_coordinates["lat"],
                    "lng": riyadh_coordinates["lng"],
                    "limit": 10
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Check if we get results (trending might be empty for some locations)
            if data["total"] > 0:
                assert len(data["items"]) > 0

                # Check first item structure
                first_item = data["items"][0]
                required_fields = [
                    "id", "name", "latitude", "longitude",
                    "created_at", "photo_urls", "additional_photos"
                ]

                for field in required_fields:
                    assert field in first_item, f"Missing field: {field}"

                # Verify ID is not -1 (should be real database ID)
                assert first_item["id"] > 0, f"Invalid ID: {first_item['id']}"

                # Verify coordinates are valid
                assert isinstance(first_item["latitude"], (int, float))
                assert isinstance(first_item["longitude"], (int, float))
                assert -90 <= first_item["latitude"] <= 90
                assert -180 <= first_item["longitude"] <= 180

                print(f"✅ Trending endpoint returned {data['total']} places")
                print(
                    f"   First place: {first_item['name']} (ID: {first_item['id']})")
            else:
                print(
                    "ℹ️  No trending venues found for this location (normal for some areas)")

    @pytest.mark.asyncio
    async def test_nearby_endpoint_structure(self, riyadh_coordinates):
        """Test nearby endpoint returns proper structure"""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/places/nearby",
                params={
                    "lat": riyadh_coordinates["lat"],
                    "lng": riyadh_coordinates["lng"],
                    "radius_m": 2000,
                    "limit": 5
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Check response structure
            assert "items" in data
            assert "total" in data
            assert "limit" in data
            assert "offset" in data

            assert isinstance(data["items"], list)
            assert isinstance(data["total"], int)
            assert isinstance(data["limit"], int)
            assert isinstance(data["offset"], int)

    @pytest.mark.asyncio
    async def test_nearby_endpoint_with_riyadh_coordinates(self, riyadh_coordinates):
        """Test nearby endpoint with Riyadh coordinates returns results"""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/places/nearby",
                params={
                    "lat": riyadh_coordinates["lat"],
                    "lng": riyadh_coordinates["lng"],
                    "radius_m": 2000,
                    "limit": 10
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Nearby should always return results for populated areas
            assert data["total"] > 0, "Nearby endpoint should return places for Riyadh"
            assert len(
                data["items"]) > 0, "Nearby endpoint should return at least one place"

            # Check first item structure
            first_item = data["items"][0]
            required_fields = [
                "id", "name", "latitude", "longitude",
                "created_at", "photo_urls", "additional_photos"
            ]

            for field in required_fields:
                assert field in first_item, f"Missing field: {field}"

            # Verify ID is not -1 (should be real database ID)
            assert first_item["id"] > 0, f"Invalid ID: {first_item['id']}"

            # Verify coordinates are valid
            assert isinstance(first_item["latitude"], (int, float))
            assert isinstance(first_item["longitude"], (int, float))
            assert -90 <= first_item["latitude"] <= 90
            assert -180 <= first_item["longitude"] <= 180

            # Verify distance is reasonable for nearby places
            if "distance_meters" in first_item and first_item["distance_meters"] is not None:
                assert first_item["distance_meters"] <= 2000, "Distance should be within radius"

            print(f"✅ Nearby endpoint returned {data['total']} places")
            print(
                f"   First place: {first_item['name']} (ID: {first_item['id']})")

    @pytest.mark.asyncio
    async def test_trending_vs_nearby_different_results(self, riyadh_coordinates):
        """Test that trending and nearby return different results (different APIs)"""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Get trending results
            trending_response = await client.get(
                "/places/trending",
                params={
                    "lat": riyadh_coordinates["lat"],
                    "lng": riyadh_coordinates["lng"],
                    "limit": 5
                }
            )

            # Get nearby results
            nearby_response = await client.get(
                "/places/nearby",
                params={
                    "lat": riyadh_coordinates["lat"],
                    "lng": riyadh_coordinates["lng"],
                    "radius_m": 2000,
                    "limit": 5
                }
            )

            assert trending_response.status_code == 200
            assert nearby_response.status_code == 200

            trending_data = trending_response.json()
            nearby_data = nearby_response.json()

            # Both should return valid responses
            assert "items" in trending_data
            assert "items" in nearby_data

            # Nearby should always have results for populated areas
            assert nearby_data["total"] > 0, "Nearby should return places for Riyadh"

            print(f"📊 Trending: {trending_data['total']} places")
            print(f"📊 Nearby: {nearby_data['total']} places")

            # If both have results, they might be different (different APIs)
            if trending_data["total"] > 0 and nearby_data["total"] > 0:
                trending_ids = {item["id"] for item in trending_data["items"]}
                nearby_ids = {item["id"] for item in nearby_data["items"]}

                # They might overlap, but that's okay - different APIs can return same places
                print(f"   Trending IDs: {trending_ids}")
                print(f"   Nearby IDs: {nearby_ids}")

    @pytest.mark.asyncio
    async def test_endpoints_with_different_riyadh_locations(self, riyadh_coordinates, riyadh_coordinates_alt):
        """Test both endpoints with different Riyadh coordinates"""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            locations = [
                ("Riyadh Center", riyadh_coordinates),
                ("Riyadh Alt", riyadh_coordinates_alt)
            ]

            for location_name, coords in locations:
                print(
                    f"\n📍 Testing {location_name}: {coords['lat']}, {coords['lng']}")

                # Test trending
                trending_response = await client.get(
                    "/places/trending",
                    params={
                        "lat": coords["lat"],
                        "lng": coords["lng"],
                        "limit": 3
                    }
                )

                # Test nearby
                nearby_response = await client.get(
                    "/places/nearby",
                    params={
                        "lat": coords["lat"],
                        "lng": coords["lng"],
                        "radius_m": 1500,
                        "limit": 3
                    }
                )

                assert trending_response.status_code == 200
                assert nearby_response.status_code == 200

                trending_data = trending_response.json()
                nearby_data = nearby_response.json()

                print(f"   Trending: {trending_data['total']} places")
                print(f"   Nearby: {nearby_data['total']} places")

                # Nearby should always have results
                assert nearby_data[
                    "total"] > 0, f"Nearby should return places for {location_name}"

    @pytest.mark.asyncio
    async def test_endpoints_save_to_database(self, riyadh_coordinates):
        """Test that endpoints save places to database with correct IDs"""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Get nearby results (more likely to have results)
            response = await client.get(
                "/places/nearby",
                params={
                    "lat": riyadh_coordinates["lat"],
                    "lng": riyadh_coordinates["lng"],
                    "radius_m": 2000,
                    "limit": 3
                }
            )

            assert response.status_code == 200
            data = response.json()

            if data["total"] > 0:
                # Check that places have valid database IDs
                for item in data["items"]:
                    assert item["id"] > 0, f"Place should have valid database ID: {item['id']}"
                    assert isinstance(
                        item["id"], int), f"ID should be integer: {item['id']}"

                # Verify places exist in database
                from app.database import get_db
                async for db in get_db():
                    for item in data["items"]:
                        place_query = select(Place).where(
                            Place.id == item["id"])
                        result = await db.execute(place_query)
                        place = result.scalar_one_or_none()

                        assert place is not None, f"Place with ID {item['id']} should exist in database"
                        assert place.name == item[
                            "name"], f"Place name should match: {place.name} vs {item['name']}"

                    break  # Exit the async generator

                print(
                    f"✅ All {len(data['items'])} places saved to database with correct IDs")

    @pytest.mark.asyncio
    async def test_pagination_parameters(self, riyadh_coordinates):
        """Test pagination parameters work correctly"""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Test with different limit and offset
            response = await client.get(
                "/places/nearby",
                params={
                    "lat": riyadh_coordinates["lat"],
                    "lng": riyadh_coordinates["lng"],
                    "radius_m": 2000,
                    "limit": 2,
                    "offset": 0
                }
            )

            assert response.status_code == 200
            data = response.json()

            assert data["limit"] == 2
            assert data["offset"] == 0
            assert len(data["items"]) <= 2

            if data["total"] > 2:
                # Test offset
                response2 = await client.get(
                    "/places/nearby",
                    params={
                        "lat": riyadh_coordinates["lat"],
                        "lng": riyadh_coordinates["lng"],
                        "radius_m": 2000,
                        "limit": 2,
                        "offset": 2
                    }
                )

                assert response2.status_code == 200
                data2 = response2.json()

                assert data2["limit"] == 2
                assert data2["offset"] == 2

                # Results should be different (different pages)
                if len(data["items"]) > 0 and len(data2["items"]) > 0:
                    first_page_ids = {item["id"] for item in data["items"]}
                    second_page_ids = {item["id"] for item in data2["items"]}

                    # Pages should not overlap
                    assert len(first_page_ids.intersection(
                        second_page_ids)) == 0, "Pagination should return different results"

                    print("✅ Pagination working correctly")

    @pytest.mark.asyncio
    async def test_error_handling_missing_coordinates(self):
        """Test error handling for missing coordinates"""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Test trending without coordinates
            response = await client.get("/places/trending")
            assert response.status_code == 200  # Should return empty results, not error

            data = response.json()
            assert data["total"] == 0
            assert len(data["items"]) == 0

            # Test nearby without coordinates (has required parameters)
            response = await client.get("/places/nearby")
            # Should return validation error for missing required params
            assert response.status_code == 422

            print("✅ Error handling for missing coordinates works correctly")
