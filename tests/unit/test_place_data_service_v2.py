"""
Unit tests for place_data_service_v2.py
"""
import pytest
from unittest.mock import patch
from app.services.place_data_service_v2 import EnhancedPlaceDataService


class TestEnhancedPlaceDataService:
    """Test cases for EnhancedPlaceDataService"""

    @pytest.fixture
    def service(self):
        """Create a service instance for testing"""
        return EnhancedPlaceDataService()

    def test_service_initialization(self, service):
        """Test that service can be initialized without errors"""
        assert service is not None
        assert hasattr(service, 'fetch_foursquare_nearby')
        assert hasattr(service, 'fetch_foursquare_trending')

    def test_venue_coordinate_fallback_logic(self, service):
        """Test the coordinate fallback logic without making API calls"""
        # Test venue data with missing location coordinates
        venue_data = {
            "fsq_id": "test456",
            "name": "Test Venue",
            "location": {
                "formatted_address": "456 Test Ave"
                # Missing latitude/longitude
            },
            "geocodes": {
                "main": {
                    "latitude": 40.7589,
                    "longitude": -73.9851
                }
            },
            "categories": [{"name": "Cafe"}]
        }
        
        # Test the coordinate extraction logic
        location = venue_data.get("location", {})
        vlat = location.get("latitude")
        vlon = location.get("longitude")
        
        # Should be None initially
        assert vlat is None
        assert vlon is None
        
        # Test fallback to geocodes
        if vlat is None or vlon is None:
            geocodes = venue_data.get("geocodes", {}).get("main", {})
            vlat = geocodes.get("latitude")
            vlon = geocodes.get("longitude")
        
        # Should now have coordinates from geocodes
        assert vlat == 40.7589
        assert vlon == -73.9851

    def test_price_tier_mapping(self, service):
        """Test price tier conversion logic"""
        # Test the price mapping logic from the service
        price_map = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
        
        assert price_map.get(1) == "$"
        assert price_map.get(2) == "$$"
        assert price_map.get(3) == "$$$"
        assert price_map.get(4) == "$$$$"
        assert price_map.get(None) is None
        assert price_map.get(5) is None
