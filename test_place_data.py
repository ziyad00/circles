#!/usr/bin/env python3
"""
Test script for place data functionality
"""

import asyncio
import httpx
import json
from datetime import datetime


async def test_place_data_endpoints():
    """Test the new place data endpoints"""
    print("🏢 Testing Place Data Integration")
    print("=" * 50)
    print(f"Time: {datetime.now()}")
    print()

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:

        # Test 1: External place suggestions
        print("1️⃣ Testing Place Suggestions")
        try:
            response = await client.get("/places/external/suggestions", params={
                "query": "coffee",
                "limit": 5
            })
            if response.status_code == 200:
                suggestions = response.json()
                print(f"   ✅ Found {len(suggestions)} coffee places")
                if suggestions:
                    first_place = suggestions[0]
                    print(
                        f"   📍 Example: {first_place['name']} at {first_place['latitude']:.4f}, {first_place['longitude']:.4f}")
            else:
                print(f"   ❌ Failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")

        print()

        # Test 2: External place search
        print("2️⃣ Testing Place Search")
        try:
            response = await client.get("/places/external/search", params={
                "lat": 37.7749,
                "lon": -122.4194,
                "radius": 5000,
                "query": "restaurant"
            })
            if response.status_code == 200:
                places = response.json()
                print(f"   ✅ Found {len(places)} restaurants in San Francisco")
                if places:
                    first_place = places[0]
                    print(f"   📍 Example: {first_place['name']}")
                    print(
                        f"   🏷️  Categories: {first_place.get('categories', 'N/A')}")
                    print(f"   🌟 Rating: {first_place.get('rating', 'N/A')}")
            else:
                print(f"   ❌ Failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")

        print()

        # Test 3: Test endpoint
        print("3️⃣ Testing Basic Endpoint")
        try:
            response = await client.get("/places/external/test")
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ {result['message']}")
            else:
                print(f"   ❌ Failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")

        print()
        print("=" * 50)
        print("🎉 Place Data Integration Test Complete!")


if __name__ == "__main__":
    asyncio.run(test_place_data_endpoints())
