#!/usr/bin/env python3
"""
Initial Place Seeding Script
Seeds major cities with OSM Overpass data
"""

import sys
import os
import asyncio
from datetime import datetime

# Ensure project root on path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import get_db
from app.services.place_data_service_v2 import enhanced_place_data_service

# Major Saudi cities to seed
MAJOR_CITIES = [
    {
        "name": "Riyadh",
        "bbox": [24.7136, 46.6753, 24.8333, 46.8000],
        "description": "Riyadh downtown and business district"
    },
    {
        "name": "Jeddah",
        "bbox": [21.4858, 39.1925, 21.6000, 39.2500],
        "description": "Jeddah downtown and corniche area"
    },
    {
        "name": "Dammam",
        "bbox": [26.4207, 50.0888, 26.5000, 50.1500],
        "description": "Dammam city center"
    },
    {
        "name": "Mecca",
        "bbox": [21.4225, 39.8262, 21.5000, 39.9000],
        "description": "Mecca holy city area"
    },
    {
        "name": "Medina",
        "bbox": [24.5247, 39.5692, 24.6000, 39.6500],
        "description": "Medina holy city area"
    },
    {
        "name": "Taif",
        "bbox": [21.2703, 40.4158, 21.3500, 40.5000],
        "description": "Taif city center"
    },
    {
        "name": "Abha",
        "bbox": [18.2164, 42.5053, 18.3000, 42.6000],
        "description": "Abha city center"
    },
    {
        "name": "Tabuk",
        "bbox": [28.3835, 36.5664, 28.4500, 36.6500],
        "description": "Tabuk city center"
    },
    {
        "name": "Al-Khobar",
        "bbox": [26.2795, 50.2084, 26.3500, 50.3000],
        "description": "Al-Khobar city center"
    },
    {
        "name": "Dhahran",
        "bbox": [26.2885, 50.1139, 26.3500, 50.2000],
        "description": "Dhahran city center"
    }
]


async def seed_city(city_data):
    """Seed a single city"""
    print(f"🌱 Seeding {city_data['name']}...")
    start_time = datetime.now()

    try:
        async for db in get_db():
            seeded_count = await enhanced_place_data_service.seed_from_osm_overpass(
                db, city_data['bbox']
            )
            processing_time = (datetime.now() - start_time).total_seconds()

            print(
                f"   ✅ {city_data['name']}: {seeded_count} places in {processing_time:.2f}s")
            return seeded_count

    except Exception as e:
        print(f"   ❌ {city_data['name']}: Failed - {str(e)}")
        return 0


async def seed_all_cities():
    """Seed all major cities"""
    print("🚀 Starting Initial Place Seeding")
    print("=" * 50)
    print(f"Time: {datetime.now()}")
    print()

    total_seeded = 0
    successful_cities = 0

    for city in MAJOR_CITIES:
        seeded_count = await seed_city(city)
        if seeded_count > 0:
            successful_cities += 1
            total_seeded += seeded_count
        print()

    print("=" * 50)
    print(f"🎉 Seeding Complete!")
    print(f"📊 Results:")
    print(f"   • Cities seeded: {successful_cities}/{len(MAJOR_CITIES)}")
    print(f"   • Total places: {total_seeded}")
    print(f"   • Average per city: {total_seeded/successful_cities:.1f}" if successful_cities >
          0 else "   • Average per city: 0")


async def seed_specific_city(city_name):
    """Seed a specific city by name"""
    city = next(
        (c for c in MAJOR_CITIES if c['name'].lower() == city_name.lower()), None)

    if not city:
        print(f"❌ City '{city_name}' not found in predefined list")
        print("Available cities:")
        for c in MAJOR_CITIES:
            print(f"   • {c['name']}")
        return

    await seed_city(city)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Seed specific city
        city_name = sys.argv[1]
        asyncio.run(seed_specific_city(city_name))
    else:
        # Seed all cities
        asyncio.run(seed_all_cities())
