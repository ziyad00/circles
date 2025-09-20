"""
Integration tests for Places API
"""
import asyncio
from typing import Dict, Any, Optional

from ..utils.base_test import BaseTest, TestConfig
from ..utils.http_client import TestHTTPClient, APIResponse
from ..utils.test_helpers import TestDataFactory, TestAssertions, TestFixtures


class PlacesAPITest(BaseTest):
    """Test places API endpoints"""

    def __init__(self, config: TestConfig = None):
        super().__init__(config)
        self.client = TestHTTPClient(self.config.base_url, self.config.timeout)
        self.test_place_id: Optional[int] = None

    async def teardown(self):
        """Cleanup after tests"""
        await self.client.close()
        await super().teardown()

    async def test_health_check(self) -> Optional[Dict[str, Any]]:
        """Test health endpoint"""
        response = APIResponse(await self.client.get("/health"))
        if response.is_success():
            return response.json
        return None

    async def test_nearby_places(self) -> Optional[Dict[str, Any]]:
        """Test nearby places endpoint (no auth required)"""
        response = APIResponse(await self.client.get(
            "/places/nearby",
            params={
                "lat": 40.7128,
                "lng": -74.0060,
                "radius_m": 1000,
                "limit": 10
            }
        ))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_trending_places(self) -> Optional[Dict[str, Any]]:
        """Test trending places endpoint (no auth required)"""
        response = APIResponse(await self.client.get(
            "/places/trending",
            params={
                "lat": 40.7128,
                "lng": -74.0060,
                "time_window": "24h",
                "limit": 10
            }
        ))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_global_trending(self) -> Optional[Dict[str, Any]]:
        """Test global trending places endpoint (no auth required)"""
        response = APIResponse(await self.client.get(
            "/places/trending/global",
            params={
                "lat": 40.7128,
                "lng": -74.0060,
                "limit": 10
            }
        ))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_create_place(self) -> Optional[Dict[str, Any]]:
        """Test create place endpoint (auth required)"""
        place_data = TestFixtures.get_sample_place_data()
        response = APIResponse(await self.client.post(
            "/places/",
            json_data=place_data,
            headers=self.get_headers()
        ))
        if response.is_success():
            data = response.json
            self.test_place_id = data.get("id")
            TestAssertions.assert_json_structure(
                response, ["id", "name", "created_at"])
            return data
        return None

    async def test_get_place(self) -> Optional[Dict[str, Any]]:
        """Test get specific place endpoint"""
        if not self.test_place_id:
            return None

        response = APIResponse(await self.client.get(f"/places/{self.test_place_id}"))
        if response.is_success():
            TestAssertions.assert_json_structure(
                response, ["id", "name", "created_at"])
            return response.json
        return None

    async def test_place_search(self) -> Optional[Dict[str, Any]]:
        """Test place search endpoint (auth required)"""
        search_data = {
            "query": "coffee",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "radius_km": 5,
            "limit": 10
        }
        response = APIResponse(await self.client.post(
            "/places/search/advanced",
            json_data=search_data,
            headers=self.get_headers()
        ))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_place_recommendations(self) -> Optional[Dict[str, Any]]:
        """Test place recommendations endpoint (auth required)"""
        response = APIResponse(await self.client.get(
            "/places/recommendations",
            params={
                "lat": 40.7128,
                "lng": -74.0060,
                "limit": 10
            },
            headers=self.get_headers()
        ))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_place_stats(self) -> Optional[Dict[str, Any]]:
        """Test place stats endpoint"""
        if not self.test_place_id:
            return None

        response = APIResponse(await self.client.get(f"/places/{self.test_place_id}/stats"))
        if response.is_success():
            TestAssertions.assert_json_structure(
                response, ["place_id", "reviews_count", "active_checkins"])
            return response.json
        return None

    async def test_place_photos(self) -> Optional[Dict[str, Any]]:
        """Test place photos endpoint"""
        if not self.test_place_id:
            return None

        response = APIResponse(await self.client.get(f"/places/{self.test_place_id}/photos"))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_place_reviews(self) -> Optional[Dict[str, Any]]:
        """Test place reviews endpoint"""
        if not self.test_place_id:
            return None

        response = APIResponse(await self.client.get(f"/places/{self.test_place_id}/reviews"))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_place_whos_here(self) -> Optional[Dict[str, Any]]:
        """Test place who's here endpoint"""
        if not self.test_place_id:
            return None

        response = APIResponse(await self.client.get(f"/places/{self.test_place_id}/whos-here"))
        if response.is_success():
            TestAssertions.assert_pagination(response)
            return response.json
        return None

    async def test_place_whos_here_count(self) -> Optional[Dict[str, Any]]:
        """Test place who's here count endpoint"""
        if not self.test_place_id:
            return None

        response = APIResponse(await self.client.get(f"/places/{self.test_place_id}/whos-here-count"))
        if response.is_success():
            data = response.json
            assert "count" in data, "Response should contain count"
            return data
        return None

    async def test_places_lookups(self) -> Optional[Dict[str, Any]]:
        """Test places lookup endpoints"""
        # Test countries lookup
        response = APIResponse(await self.client.get("/places/lookups/countries"))
        if response.is_success():
            data = response.json
            assert isinstance(data, list), "Countries should be a list"
            return {"countries": len(data)}
        return None

    async def test_places_cities_lookup(self) -> Optional[Dict[str, Any]]:
        """Test cities lookup endpoint"""
        response = APIResponse(await self.client.get("/places/lookups/cities"))
        if response.is_success():
            data = response.json
            assert isinstance(data, list), "Cities should be a list"
            return {"cities": len(data)}
        return None

    async def test_places_neighborhoods_lookup(self) -> Optional[Dict[str, Any]]:
        """Test neighborhoods lookup endpoint"""
        response = APIResponse(await self.client.get("/places/lookups/neighborhoods"))
        if response.is_success():
            data = response.json
            assert isinstance(data, list), "Neighborhoods should be a list"
            return {"neighborhoods": len(data)}
        return None

    async def run_tests(self):
        """Run all places tests"""
        self._log("🏢 Testing Places API Endpoints...")

        # Test 1: Health check
        await self.run_test("Health Check", self.test_health_check)

        # Test 2: Public endpoints (no auth required)
        await self.run_test("Nearby Places", self.test_nearby_places)
        await self.run_test("Trending Places", self.test_trending_places)
        await self.run_test("Global Trending", self.test_global_trending)

        # Test 3: Lookup endpoints
        await self.run_test("Countries Lookup", self.test_places_lookups)
        await self.run_test("Cities Lookup", self.test_places_cities_lookup)
        await self.run_test("Neighborhoods Lookup", self.test_places_neighborhoods_lookup)

        # Test 4: Create place (auth required)
        await self.run_test("Create Place", self.test_create_place)

        if self.test_place_id:
            # Test 5: Place details
            await self.run_test("Get Place", self.test_get_place)
            await self.run_test("Place Stats", self.test_place_stats)
            await self.run_test("Place Photos", self.test_place_photos)
            await self.run_test("Place Reviews", self.test_place_reviews)
            await self.run_test("Place Who's Here", self.test_place_whos_here)
            await self.run_test("Place Who's Here Count", self.test_place_whos_here_count)

        # Test 6: Search and recommendations (auth required)
        await self.run_test("Place Search", self.test_place_search)
        await self.run_test("Place Recommendations", self.test_place_recommendations)


async def main():
    """Main test runner"""
    config = TestConfig(verbose=True)
    test = PlacesAPITest(config)
    await test.execute()

if __name__ == "__main__":
    asyncio.run(main())
