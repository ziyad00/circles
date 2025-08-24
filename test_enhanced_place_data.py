#!/usr/bin/env python3
"""
Test script for Enhanced Place Data Integration
"""

import asyncio
import httpx
import json
from datetime import datetime


async def test_enhanced_place_data():
    """Test the enhanced place data endpoints"""
    print("🚀 Testing Enhanced Place Data Integration")
    print("=" * 60)
    print(f"Time: {datetime.now()}")
    print()

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        
        # Test 1: Seed places from OSM Overpass
        print("1️⃣ Testing OSM Overpass Seeding")
        try:
            # Seed a small area in San Francisco
            response = await client.post("/places/seed/from-osm", params={
                "min_lat": 37.7749,
                "min_lon": -122.4194,
                "max_lat": 37.7849,
                "max_lon": -122.4094
            })
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Seeded {data['seeded_count']} places")
                print(f"   ⏱️  Processing time: {data['processing_time_seconds']:.2f}s")
                print(f"   📍 BBox: {data['bbox']}")
            else:
                print(f"   ❌ Failed: {response.status_code}")
                print(f"   📄 Response: {response.text}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print()
        
        # Test 2: Enhanced search with enrichment
        print("2️⃣ Testing Enhanced Search")
        try:
            response = await client.get("/places/search/enhanced", params={
                "lat": 37.7749,
                "lon": -122.4194,
                "radius": 2000,
                "query": "coffee",
                "limit": 5,
                "enable_enrichment": True
            })
            
            if response.status_code == 200:
                places = response.json()
                print(f"   ✅ Found {len(places)} places")
                if places:
                    first_place = places[0]
                    print(f"   📍 Top result: {first_place['name']}")
                    print(f"   🌟 Quality score: {first_place.get('quality_score', 'N/A')}")
                    print(f"   📊 Rating: {first_place.get('rating', 'N/A')}")
                    print(f"   📞 Phone: {first_place.get('phone', 'N/A')}")
                    print(f"   🌐 Website: {first_place.get('website', 'N/A')}")
            else:
                print(f"   ❌ Failed: {response.status_code}")
                print(f"   📄 Response: {response.text}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print()
        
        # Test 3: Search without enrichment
        print("3️⃣ Testing Search Without Enrichment")
        try:
            response = await client.get("/places/search/enhanced", params={
                "lat": 37.7749,
                "lon": -122.4194,
                "radius": 2000,
                "query": "restaurant",
                "limit": 3,
                "enable_enrichment": False
            })
            
            if response.status_code == 200:
                places = response.json()
                print(f"   ✅ Found {len(places)} places (no enrichment)")
                if places:
                    for i, place in enumerate(places[:2], 1):
                        print(f"   {i}. {place['name']} (Quality: {place.get('quality_score', 'N/A')})")
            else:
                print(f"   ❌ Failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print()
        
        # Test 4: Enrichment statistics
        print("4️⃣ Testing Enrichment Statistics")
        try:
            response = await client.get("/places/stats/enrichment")
            
            if response.status_code == 200:
                stats = response.json()
                print(f"   📊 Total places: {stats['total_places']}")
                print(f"   🔄 Enriched places: {stats['enriched_places']}")
                print(f"   📈 Enrichment rate: {stats['enrichment_rate']:.1f}%")
                print(f"   ⭐ Average quality score: {stats['average_quality_score']}")
                print(f"   🕒 TTL compliance rate: {stats['ttl_compliance_rate']:.1f}%")
                print(f"   📍 Source distribution: {stats['source_distribution']}")
            else:
                print(f"   ❌ Failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print()
        
        # Test 5: Manual enrichment (if we have places)
        print("5️⃣ Testing Manual Enrichment")
        try:
            # First get a place to enrich
            search_response = await client.get("/places/search/enhanced", params={
                "lat": 37.7749,
                "lon": -122.4194,
                "radius": 5000,
                "limit": 1,
                "enable_enrichment": False
            })
            
            if search_response.status_code == 200:
                places = search_response.json()
                if places:
                    place_id = places[0]['id']
                    print(f"   🎯 Testing enrichment for place ID: {place_id}")
                    
                    # Try to enrich the place
                    enrich_response = await client.post(f"/places/enrich/{place_id}", params={
                        "force": False
                    })
                    
                    if enrich_response.status_code == 200:
                        enrich_data = enrich_response.json()
                        print(f"   ✅ Enrichment result: {enrich_data['message']}")
                        print(f"   🌟 Quality score: {enrich_data['quality_score']}")
                        print(f"   🔄 Enriched: {enrich_data['enriched']}")
                    else:
                        print(f"   ❌ Enrichment failed: {enrich_response.status_code}")
                else:
                    print("   ⚠️  No places found to test enrichment")
            else:
                print(f"   ❌ Search failed: {search_response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")

        print()
        print("=" * 60)
        print("🎉 Enhanced Place Data Integration Test Complete!")
        print()
        print("📋 Summary of New Endpoints:")
        print("   • POST /places/seed/from-osm - Seed places from OSM Overpass")
        print("   • GET /places/search/enhanced - Enhanced search with enrichment")
        print("   • POST /places/enrich/{place_id} - Manual place enrichment")
        print("   • GET /places/stats/enrichment - Enrichment statistics")
        print()
        print("🚀 Ready for production with Foursquare API key!")


if __name__ == "__main__":
    asyncio.run(test_enhanced_place_data())
