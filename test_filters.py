#!/usr/bin/env python3
"""
Test script to verify trending and nearby endpoint filters work with real data.
"""
import asyncio
import httpx
import json
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

async def test_endpoint(client: httpx.AsyncClient, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Test an endpoint with given parameters."""
    try:
        response = await client.get(f"{BASE_URL}{endpoint}", params=params)
        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "total_items": len(data.get("items", [])),
                "external_count": data.get("external_count", 0),
                "items": data.get("items", [])[:3],  # First 3 items for inspection
                "external_results": data.get("external_results", [])[:3]  # First 3 external
            }
        else:
            return {
                "success": False,
                "status_code": response.status_code,
                "error": response.text
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

async def test_filters():
    """Test various filter combinations on trending and nearby endpoints."""
    async with httpx.AsyncClient(timeout=30.0) as client:

        # Test coordinates (San Francisco area)
        lat, lng = 37.7749, -122.4194

        print("🧪 Testing Trending and Nearby Endpoint Filters\n")

        # Test cases for both endpoints
        test_cases = [
            {
                "name": "Basic Request (No Filters)",
                "params": {"lat": lat, "lng": lng, "limit": 5}
            },
            {
                "name": "Search Filter (Coffee)",
                "params": {"lat": lat, "lng": lng, "q": "coffee", "limit": 5}
            },
            {
                "name": "Category Filter (Cafe)",
                "params": {"lat": lat, "lng": lng, "place_type": "cafe", "limit": 5}
            },
            {
                "name": "Min Rating Filter (4.0+)",
                "params": {"lat": lat, "lng": lng, "min_rating": 4.0, "limit": 5}
            },
            {
                "name": "Price Tier Filter ($$)",
                "params": {"lat": lat, "lng": lng, "price_tier": "$$", "limit": 5}
            },
            {
                "name": "City Filter (San Francisco)",
                "params": {"lat": lat, "lng": lng, "city": "San Francisco", "limit": 5}
            },
            {
                "name": "Combined Filters (Coffee + Rating + Price)",
                "params": {"lat": lat, "lng": lng, "q": "coffee", "min_rating": 3.5, "price_tier": "$", "limit": 5}
            }
        ]

        endpoints = [
            ("/places/trending", "TRENDING"),
            ("/places/nearby", "NEARBY")
        ]

        for endpoint, name in endpoints:
            print(f"🎯 Testing {name} Endpoint")
            print("=" * 50)

            for test_case in test_cases:
                print(f"\n📋 {test_case['name']}")
                print(f"   Params: {test_case['params']}")

                result = await test_endpoint(client, endpoint, test_case['params'])

                if result["success"]:
                    print(f"   ✅ Success: {result['total_items']} items, {result['external_count']} external")

                    # Show sample items if any
                    if result["items"]:
                        print(f"   📍 Sample DB items:")
                        for i, item in enumerate(result["items"][:2], 1):
                            name = item.get("name", "Unknown")
                            rating = item.get("rating", "N/A")
                            price = item.get("price_tier", "N/A")
                            categories = item.get("categories", "N/A")
                            print(f"      {i}. {name} | Rating: {rating} | Price: {price} | Cat: {categories}")

                    # Show sample external results if any
                    if result["external_results"]:
                        print(f"   🌐 Sample External items:")
                        for i, item in enumerate(result["external_results"][:2], 1):
                            name = item.get("name", "Unknown")
                            rating = item.get("rating", "N/A")
                            price = item.get("price_tier", "N/A")
                            categories = item.get("categories", "N/A")
                            source = item.get("data_source", "Unknown")
                            print(f"      {i}. {name} | Rating: {rating} | Price: {price} | Source: {source}")
                else:
                    print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")

            print("\n")

if __name__ == "__main__":
    print("Starting filter tests...")
    print("Make sure your FastAPI server is running on localhost:8000\n")
    asyncio.run(test_filters())
    print("✅ Filter tests completed!")