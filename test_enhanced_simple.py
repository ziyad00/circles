#!/usr/bin/env python3
"""
Simple test for Enhanced Place Data Integration
"""

import asyncio
import httpx
from datetime import datetime


async def test_enhanced_endpoints():
    """Test the enhanced place data endpoints"""
    print("🚀 Testing Enhanced Place Data Endpoints")
    print("=" * 50)
    print(f"Time: {datetime.now()}")
    print()

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        
        # Test 1: Health check
        print("1️⃣ Testing Health Check")
        try:
            response = await client.get("/health")
            if response.status_code == 200:
                print(f"   ✅ Health check passed: {response.json()}")
            else:
                print(f"   ❌ Health check failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print()
        
        # Test 2: Enrichment stats
        print("2️⃣ Testing Enrichment Stats")
        try:
            response = await client.get("/places/stats/enrichment")
            if response.status_code == 200:
                stats = response.json()
                print(f"   ✅ Stats endpoint working")
                print(f"   📊 Total places: {stats.get('total_places', 'N/A')}")
                print(f"   🔄 Enriched places: {stats.get('enriched_places', 'N/A')}")
            else:
                print(f"   ❌ Stats failed: {response.status_code}")
                print(f"   📄 Response: {response.text}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print()
        
        # Test 3: Enhanced search
        print("3️⃣ Testing Enhanced Search")
        try:
            response = await client.get("/places/search/enhanced", params={
                "lat": 37.7749,
                "lon": -122.4194,
                "radius": 5000,
                "limit": 5,
                "enable_enrichment": False
            })
            if response.status_code == 200:
                places = response.json()
                print(f"   ✅ Enhanced search working")
                print(f"   📍 Found {len(places)} places")
            else:
                print(f"   ❌ Enhanced search failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print()
        
        # Test 4: OSM seeding
        print("4️⃣ Testing OSM Seeding")
        try:
            response = await client.post("/places/seed/from-osm", params={
                "min_lat": 37.7749,
                "min_lon": -122.4194,
                "max_lat": 37.7849,
                "max_lon": -122.4094
            })
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ OSM seeding working")
                print(f"   🌱 Seeded {data.get('seeded_count', 0)} places")
            else:
                print(f"   ❌ OSM seeding failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")

        print()
        print("=" * 50)
        print("🎉 Enhanced Place Data Test Complete!")


if __name__ == "__main__":
    asyncio.run(test_enhanced_endpoints())
