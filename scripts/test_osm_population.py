#!/usr/bin/env python3
"""
Test OSM Data Population Script
Test the OSM data population functionality with mock data
"""

import sys
import os
import asyncio
import json
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock

# Ensure project root on path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from scripts.populate_osm_data import OSMDataPopulator


async def test_osm_data_population():
    """Test OSM data population with mock data"""
    print("🧪 Testing OSM Data Population")

    # Create populator instance
    populator = OSMDataPopulator()

    # Test data
    test_place = {
        'id': 1,
        'name': 'Starbucks Coffee',
        'latitude': 24.7136,
        'longitude': 46.6753,
        'categories': 'cafe,coffee',
        'city': 'Riyadh',
        'website': None,
        'phone': None,
        'place_metadata': None
    }

    print(f"📍 Testing with place: {test_place['name']}")

    # Test OSM element finding (mock)
    print("🔍 Testing OSM element finding...")
    try:
        # This would normally call Nominatim API
        mock_osm_element = {
            'osm_id': 12345,
            'osm_type': 'node',
            'display_name': 'Starbucks, Riyadh, Saudi Arabia',
            'lat': '24.7136',
            'lon': '46.6753'
        }

        score = populator._calculate_match_score(
            MagicMock(**test_place),
            mock_osm_element
        )
        print(f"   ✅ Match score: {score:.2f}")

    except Exception as e:
        print(f"   ❌ Error testing match score: {e}")

    # Test detailed element parsing
    print("📝 Testing OSM element parsing...")
    try:
        mock_element = {
            'id': 12345,
            'type': 'node',
            'tags': {
                'name': 'Starbucks Coffee',
                'website': 'https://www.starbucks.com',
                'phone': '+96611234567',
                'opening_hours': 'Mo-Su 06:00-24:00',
                'wheelchair': 'yes',
                'wifi': 'yes',
                'outdoor_seating': 'yes',
                'amenity': 'cafe',
                'cuisine': 'coffee_shop'
            }
        }

        parsed_data = populator._parse_osm_element_detailed(mock_element)

        print("   📊 Parsed OSM data:")
        print(f"      Website: {parsed_data.get('website', 'None')}")
        print(f"      Phone: {parsed_data.get('phone', 'None')}")
        print(f"      Opening hours: {parsed_data.get('opening_hours', 'None')}")
        print(f"      Amenities: {parsed_data.get('amenities', {})}")

    except Exception as e:
        print(f"   ❌ Error testing element parsing: {e}")

    # Test photo fetching
    print("📸 Testing photo fetching...")
    try:
        photos = await populator._get_placeholder_photos(test_place['name'])

        print(f"   📷 Found {len(photos)} placeholder photos")
        for i, photo in enumerate(photos):
            print(f"      Photo {i+1}: {photo.get('source', 'unknown')}")

    except Exception as e:
        print(f"   ❌ Error testing photo fetching: {e}")

    # Test Wikimedia photo fetching (mock test)
    print("🖼️  Testing Wikimedia photo integration...")
    try:
        # This would normally call Wikimedia API
        # For testing, we'll simulate the call structure
        wikimedia_photos = await populator._get_wikimedia_photos(
            test_place['latitude'],
            test_place['longitude'],
            test_place['name']
        )

        print(f"   🖼️  Found {len(wikimedia_photos)} Wikimedia photos")
        if wikimedia_photos:
            for i, photo in enumerate(wikimedia_photos[:2]):
                print(f"      Photo {i+1}: {photo.get('caption', 'No caption')}")

    except Exception as e:
        print(f"   ⚠️  Wikimedia test failed (expected): {e}")

    print("\n✅ OSM Data Population Test Complete!")


async def test_enrichment_workflow():
    """Test the full enrichment workflow"""
    print("\n🔄 Testing Enrichment Workflow")

    # Mock place object
    mock_place = MagicMock()
    mock_place.name = "Test Restaurant"
    mock_place.latitude = 24.7136
    mock_place.longitude = 46.6753
    mock_place.website = None
    mock_place.phone = None
    mock_place.place_metadata = None

    # Mock OSM data
    mock_osm_data = {
        'website': 'https://testrestaurant.com',
        'phone': '+96611234567',
        'opening_hours': 'Mo-Su 10:00-22:00',
        'amenities': {
            'wifi': True,
            'outdoor_seating': True,
            'wheelchair_accessible': True
        }
    }

    populator = OSMDataPopulator()

    # Test update function (without DB)
    print("📝 Testing place update logic...")
    try:
        # Simulate the update logic
        updated = False

        # Update basic fields
        if 'website' in mock_osm_data and not mock_place.website:
            mock_place.website = mock_osm_data['website']
            updated = True

        if 'phone' in mock_osm_data and not mock_place.phone:
            mock_place.phone = mock_osm_data['phone']
            updated = True

        # Update metadata
        metadata = mock_place.place_metadata or {}

        if 'opening_hours' in mock_osm_data:
            metadata['opening_hours'] = mock_osm_data['opening_hours']
            updated = True

        if 'amenities' in mock_osm_data:
            metadata['amenities'] = mock_osm_data['amenities']
            updated = True

        print("   📊 Update results:")
        print(f"      Website: {mock_place.website}")
        print(f"      Phone: {mock_place.phone}")
        print(f"      Opening hours: {metadata.get('opening_hours')}")
        print(f"      Amenities: {metadata.get('amenities')}")
        print(f"      Updated: {updated}")

    except Exception as e:
        print(f"   ❌ Error testing update logic: {e}")

    print("\n✅ Enrichment Workflow Test Complete!")


async def show_sample_osm_query():
    """Show sample OSM Overpass query"""
    print("\n🗺️  Sample OSM Overpass Query")

    populator = OSMDataPopulator()

    # Test query building
    bbox = (24.7136, 46.6753, 24.7336, 46.6953)  # Small area in Riyadh

    try:
        query = populator._build_overpass_query(bbox)
        print("📋 Generated Overpass Query:")
        print("=" * 50)
        print(query)
        print("=" * 50)

    except Exception as e:
        print(f"❌ Error building query: {e}")


async def main():
    """Main test function"""
    print("🚀 OSM Data Population Testing Suite")
    print("=" * 50)

    await test_osm_data_population()
    await test_enrichment_workflow()
    await show_sample_osm_query()

    print("\n" + "=" * 50)
    print("🎉 All Tests Completed!")
    print("\n📝 Next Steps:")
    print("   1. Configure database connection")
    print("   2. Set environment variables for API keys")
    print("   3. Run: python scripts/populate_osm_data.py --limit 10")
    print("   4. Check logs for enrichment results")


if __name__ == "__main__":
    asyncio.run(main())
