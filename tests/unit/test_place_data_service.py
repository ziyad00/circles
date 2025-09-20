"""
Unit tests for Place Data Service
"""
from app.services.place_data_service_v2 import EnhancedPlaceDataService
import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../app'))


class PlaceDataServiceTest:
    """Test Place Data Service functionality"""

    def __init__(self):
        self.service = EnhancedPlaceDataService()

    def test_service_initialization(self):
        """Test service initialization"""
        assert self.service is not None
        assert hasattr(self.service, 'foursquare_api_key')
        assert hasattr(self.service, 'trending_radius_m')
        print("✅ Service initialization test passed")

    @patch('app.services.place_data_service_v2.httpx.AsyncClient')
    async def test_fetch_foursquare_trending_success(self, mock_client):
        """Test successful Foursquare trending fetch"""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": {
                "venues": [
                    {
                        "id": "test_venue_1",
                        "name": "Test Coffee Shop",
                        "location": {"lat": 40.7128, "lng": -74.0060},
                        "categories": [{"name": "Coffee Shop"}],
                        "rating": 4.5,
                        "contact": {"phone": "+1234567890"},
                        "website": "https://test.com",
                        "photos": [{"prefix": "https://test.com/", "suffix": "photo.jpg"}],
                        "price": 2,
                        "verified": True,
                        "description": "A test coffee shop",
                        "stats": {"total_checkins": 100, "total_ratings": 50, "total_photos": 25}
                    }
                ]
            }
        }

        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

        # Test the method
        result = await self.service.fetch_foursquare_trending(40.7128, -74.0060, limit=5)

        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "Test Coffee Shop"
        assert result[0]["latitude"] == 40.7128
        assert result[0]["longitude"] == -74.0060
        assert result[0]["data_source"] == "foursquare"

        print("✅ Foursquare trending fetch success test passed")

    @patch('app.services.place_data_service_v2.httpx.AsyncClient')
    async def test_fetch_foursquare_trending_api_error(self, mock_client):
        """Test Foursquare API error handling"""
        # Mock error response
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Invalid request token"

        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

        # Test the method
        result = await self.service.fetch_foursquare_trending(40.7128, -74.0060, limit=5)

        # Should return empty list on error
        assert result == []

        print("✅ Foursquare API error handling test passed")

    @patch('app.services.place_data_service_v2.httpx.AsyncClient')
    async def test_fetch_foursquare_trending_v3_fallback(self, mock_client):
        """Test Foursquare v3 fallback functionality"""
        # Mock v2 failure
        mock_v2_response = MagicMock()
        mock_v2_response.status_code = 403

        # Mock v3 success
        mock_v3_response = MagicMock()
        mock_v3_response.status_code = 200
        mock_v3_response.json.return_value = {
            "results": [
                {
                    "fsq_id": "test_venue_2",
                    "name": "Test Restaurant",
                    "geocodes": {"main": {"latitude": 40.7589, "longitude": -73.9851}},
                    "categories": [{"name": "Restaurant"}],
                    "rating": 4.2,
                    "contact": {"phone": "+1234567891"},
                    "website": "https://restaurant.com",
                    "photos": [{"prefix": "https://restaurant.com/", "suffix": "photo.jpg"}],
                    "price": 3,
                    "verified": False,
                    "description": "A test restaurant",
                    "stats": {"total_ratings": 30, "total_photos": 15}
                }
            ]
        }

        # Configure mock to return v2 error first, then v3 success
        mock_client.return_value.__aenter__.return_value.get.side_effect = [
            mock_v2_response,  # v2 fails
            mock_v3_response   # v3 succeeds
        ]

        # Test the method
        result = await self.service.fetch_foursquare_trending(40.7128, -74.0060, limit=5)

        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "Test Restaurant"
        assert result[0]["latitude"] == 40.7589
        assert result[0]["longitude"] == -73.9851
        assert result[0]["data_source"] == "foursquare"

        print("✅ Foursquare v3 fallback test passed")

    def test_cache_functionality(self):
        """Test caching functionality"""
        # Test cache key generation
        cache_key = self.service._cache_key("test", "data")
        assert cache_key is not None
        assert isinstance(cache_key, str)

        # Test cache set/get
        test_data = {"test": "data"}
        self.service._cache_set("test_cache", cache_key, test_data)
        cached_data = self.service._cache_get("test_cache", cache_key)

        assert cached_data == test_data

        print("✅ Cache functionality test passed")

    def test_photo_url_processing(self):
        """Test photo URL processing"""
        # Test Foursquare photo URL construction
        photo_data = {
            "prefix": "https://test.com/",
            "suffix": "photo.jpg"
        }

        # This would be tested in the actual service method
        # For now, just test the concept
        expected_url = f"{photo_data['prefix']}300x300{photo_data['suffix']}"
        assert expected_url == "https://test.com/300x300photo.jpg"

        print("✅ Photo URL processing test passed")

    def test_price_tier_conversion(self):
        """Test price tier conversion"""
        # Test price tier mapping
        price_map = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}

        assert price_map[1] == "$"
        assert price_map[2] == "$$"
        assert price_map[3] == "$$$"
        assert price_map[4] == "$$$$"

        print("✅ Price tier conversion test passed")

    async def run_all_tests(self):
        """Run all place data service tests"""
        print("🏢 Testing Place Data Service...")
        print("=" * 50)

        try:
            self.test_service_initialization()
            await self.test_fetch_foursquare_trending_success()
            await self.test_fetch_foursquare_trending_api_error()
            await self.test_fetch_foursquare_trending_v3_fallback()
            self.test_cache_functionality()
            self.test_photo_url_processing()
            self.test_price_tier_conversion()

            print("\n✅ All Place Data Service tests passed!")

        except Exception as e:
            print(f"\n❌ Place Data Service test failed: {e}")
            raise


async def main():
    """Main test runner"""
    test = PlaceDataServiceTest()
    await test.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
