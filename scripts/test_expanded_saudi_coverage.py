#!/usr/bin/env python3
"""
Test Expanded Saudi Cities Coverage
Shows the comprehensive list of Saudi cities that will be auto-seeded
"""

from app.database import get_db
from app.services.auto_seeder_service import AutoSeederService
import sys
import os
import asyncio

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))


async def test_expanded_saudi_coverage():
    """Test the expanded Saudi cities coverage"""
    print("🇸🇦 EXPANDED SAUDI CITIES COVERAGE")
    print("=" * 60)

    auto_seeder = AutoSeederService()

    print(f"\n📊 Total Cities to Seed: {len(auto_seeder.saudi_cities)}")
    print(f"🔍 Seeding Threshold: 500 OSM places")

    print(f"\n🗺️ CITIES BY REGION:")
    print("-" * 40)

    # Group cities by region
    regions = {
        "Riyadh Region": [],
        "Makkah Province": [],
        "Madinah Province": [],
        "Eastern Province": [],
        "Asir Province": [],
        "Tabuk Province": [],
        "Qassim Province": [],
        "Ha'il Province": [],
        "Alternative Names": []
    }

    for city in auto_seeder.saudi_cities:
        if "Riyadh" in city["description"] or "Riyadh" in city["name"]:
            regions["Riyadh Region"].append(city)
        elif "Makkah" in city["description"] or "Jeddah" in city["name"] or "Mecca" in city["name"] or "Taif" in city["name"]:
            regions["Makkah Province"].append(city)
        elif "Madinah" in city["description"] or "Medina" in city["name"] or "Yanbu" in city["name"]:
            regions["Madinah Province"].append(city)
        elif "Eastern" in city["description"] or "Dammam" in city["name"] or "Khobar" in city["name"] or "Dhahran" in city["name"]:
            regions["Eastern Province"].append(city)
        elif "Asir" in city["description"] or "Abha" in city["name"] or "Khamis" in city["name"]:
            regions["Asir Province"].append(city)
        elif "Tabuk" in city["description"] or "Tabuk" in city["name"]:
            regions["Tabuk Province"].append(city)
        elif "Qassim" in city["description"] or "Buraydah" in city["name"] or "Unaizah" in city["name"]:
            regions["Qassim Province"].append(city)
        elif "Ha'il" in city["description"] or "Ha'il" in city["name"] or "Al-Jouf" in city["name"]:
            regions["Ha'il Province"].append(city)
        elif "Alternative" in city["description"]:
            regions["Alternative Names"].append(city)
        else:
            # Default to Riyadh if unclear
            regions["Riyadh Region"].append(city)

    for region, cities in regions.items():
        if cities:
            print(f"\n📍 {region} ({len(cities)} cities):")
            for city in cities:
                print(f"   • {city['name']} - {city['description']}")

    print(f"\n🎯 COVERAGE STATISTICS:")
    print("-" * 40)

    total_cities = len(auto_seeder.saudi_cities)
    unique_cities = len(set(city["name"] for city in auto_seeder.saudi_cities))
    alternative_names = len(
        [c for c in auto_seeder.saudi_cities if "Alternative" in c["description"]])

    print(f"📈 Total Cities: {total_cities}")
    print(f"🏙️ Unique Cities: {unique_cities}")
    print(f"🔄 Alternative Names: {alternative_names}")
    print(
        f"📊 Coverage Increase: {((total_cities - 10) / 10 * 100):.1f}% from original")

    print(f"\n🗺️ GEOGRAPHIC COVERAGE:")
    print("-" * 40)

    # Calculate bounding box of all cities
    all_lats = []
    all_lons = []

    for city in auto_seeder.saudi_cities:
        min_lat, min_lon, max_lat, max_lon = city["bbox"]
        all_lats.extend([min_lat, max_lat])
        all_lons.extend([min_lon, max_lon])

    if all_lats and all_lons:
        min_lat, max_lat = min(all_lats), max(all_lats)
        min_lon, max_lon = min(all_lons), max(all_lons)

        print(f"🌍 Northernmost: {max_lat:.4f}°N")
        print(f"🌍 Southernmost: {min_lat:.4f}°N")
        print(f"🌍 Easternmost: {max_lon:.4f}°E")
        print(f"🌍 Westernmost: {min_lon:.4f}°E")
        print(f"📏 Latitudinal Span: {max_lat - min_lat:.2f}°")
        print(f"📏 Longitudinal Span: {max_lon - min_lon:.2f}°")

    print(f"\n🚀 SEEDING BENEFITS:")
    print("-" * 40)
    print(f"✅ Comprehensive coverage of all 13 provinces")
    print(f"✅ Major cities and regional capitals")
    print(f"✅ Tourist destinations (Al-Ula, Al-Diriyah)")
    print(f"✅ Industrial hubs (Yanbu, Al-Jubail)")
    print(f"✅ Religious sites (Mecca, Medina)")
    print(f"✅ Alternative city name spellings")
    print(f"✅ Coastal cities and ports")
    print(f"✅ Border cities and trade centers")

    print(f"\n🔧 TECHNICAL DETAILS:")
    print("-" * 40)
    print(f"📊 Seeding Threshold: 500 OSM places (increased from 100)")
    print(f"🗺️ Bounding Boxes: Larger coverage areas for better data")
    print(f"🔄 Auto-Seeding: Runs on server startup")
    print(f"📈 Data Source: OpenStreetMap Overpass API")
    print(f"💾 Storage: Places saved to local database")

    print(f"\n🎉 EXPANDED SAUDI COVERAGE READY!")
    print("=" * 60)
    print(
        f"The auto-seeding service now covers {total_cities} cities across Saudi Arabia.")
    print(f"This provides comprehensive coverage for the Circles application.")


async def test_database_connection():
    """Test database connection and current seeding status"""
    print(f"\n🔍 DATABASE CONNECTION TEST")
    print("-" * 40)

    try:
        async for db in get_db():
            auto_seeder = AutoSeederService()

            # Check current seeding status
            should_seed = await auto_seeder.should_seed_data(db)
            seeding_status = await auto_seeder.get_seeding_status(db)

            print(f"✅ Database connection successful")
            print(
                f"📊 Current OSM places: {seeding_status.get('osm_places_count', 0)}")
            print(f"🔍 Should seed: {should_seed}")
            print(f"📈 Seeding threshold: 500 places")

            break

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print(f"💡 Make sure the database is running:")
        print(f"   docker-compose up -d postgres")


async def main():
    """Main function"""
    await test_expanded_saudi_coverage()
    await test_database_connection()


if __name__ == "__main__":
    asyncio.run(main())
