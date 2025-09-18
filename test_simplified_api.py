#!/usr/bin/env python3
"""
Test script to verify the simplified API architecture changes.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_schema_simplification():
    """Test that PaginatedPlaces schema has been simplified."""
    from app.schemas import PaginatedPlaces
    from pydantic import ValidationError

    # Test that PaginatedPlaces no longer has external fields
    test_data = {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0
    }

    try:
        paginated = PaginatedPlaces(**test_data)
        print("✅ PaginatedPlaces schema simplified successfully")

        # Verify external fields are not present
        assert not hasattr(paginated, 'external_results'), "external_results field should be removed"
        assert not hasattr(paginated, 'external_count'), "external_count field should be removed"
        assert not hasattr(paginated, 'external_snapshot_id'), "external_snapshot_id field should be removed"

        print("✅ External fields successfully removed from PaginatedPlaces")
        return True
    except Exception as e:
        print(f"❌ PaginatedPlaces schema test failed: {e}")
        return False

def test_endpoints_exist():
    """Test that key endpoints still exist and have correct signatures."""
    try:
        from app.routers.places import router

        # Get all routes
        routes = [route for route in router.routes]
        route_paths = [route.path for route in routes if hasattr(route, 'path')]

        # Check that key endpoints exist
        assert "/trending" in route_paths, "Trending endpoint should exist"
        assert "/nearby" in route_paths, "Nearby endpoint should exist"

        print("✅ Key endpoints (trending, nearby) exist")

        # Check that redundant search endpoints are removed
        search_endpoints = [path for path in route_paths if '/search' in path and path != '/search']
        removed_endpoints = [
            "/search",
            "/search/suggestions",
            "/search/filter-options",
            "/search/quick",
            "/search/enhanced"
        ]

        for endpoint in removed_endpoints:
            assert endpoint not in route_paths, f"Redundant endpoint {endpoint} should be removed"

        print("✅ Redundant search endpoints successfully removed")
        return True
    except Exception as e:
        print(f"❌ Endpoint test failed: {e}")
        return False

def test_place_data_service():
    """Test that save functions exist in place data service."""
    try:
        from app.services.place_data_service_v2 import enhanced_place_data_service

        # Check that save functions exist
        assert hasattr(enhanced_place_data_service, 'save_foursquare_place_to_db'), "save_foursquare_place_to_db should exist"
        assert hasattr(enhanced_place_data_service, 'save_foursquare_places_to_db'), "save_foursquare_places_to_db should exist"

        print("✅ Foursquare save functions exist in place data service")
        return True
    except Exception as e:
        print(f"❌ Place data service test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Testing Simplified API Architecture\n")

    tests = [
        test_schema_simplification,
        test_endpoints_exist,
        test_place_data_service,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
        print()

    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Simplified API architecture is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please review the changes.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)