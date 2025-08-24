"""
Auto Seeder Service
Automatically seeds Saudi cities data when server starts (if not already seeded)
"""

import asyncio
import logging
from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models import Place
from ..services.place_data_service_v2 import enhanced_place_data_service

logger = logging.getLogger(__name__)


class AutoSeederService:
    """Service for automatic seeding of Saudi cities data"""

    def __init__(self):
        self.saudi_cities = [
            # Major Saudi cities with their bounding boxes
            {
                "name": "Riyadh",
                "bbox": (24.7136, 46.6753, 24.7336, 46.6953),
                "description": "Capital city of Saudi Arabia"
            },
            {
                "name": "Jeddah",
                "bbox": (21.4858, 39.1925, 21.5058, 39.2125),
                "description": "Major port city on the Red Sea"
            },
            {
                "name": "Dammam",
                "bbox": (26.4207, 50.0888, 26.4407, 50.1088),
                "description": "Capital of Eastern Province"
            },
            {
                "name": "Mecca",
                "bbox": (21.4225, 39.8262, 21.4425, 39.8462),
                "description": "Holy city and religious capital"
            },
            {
                "name": "Medina",
                "bbox": (24.5247, 39.5692, 24.5447, 39.5892),
                "description": "Second holiest city in Islam"
            },
            {
                "name": "Taif",
                "bbox": (21.2703, 40.4158, 21.2903, 40.4358),
                "description": "Mountain resort city"
            },
            {
                "name": "Abha",
                "bbox": (18.2164, 42.5053, 18.2364, 42.5253),
                "description": "Capital of Asir Province"
            },
            {
                "name": "Tabuk",
                "bbox": (28.3835, 36.5664, 28.4035, 36.5864),
                "description": "Capital of Tabuk Province"
            },
            {
                "name": "Al-Khobar",
                "bbox": (26.2795, 50.2084, 26.2995, 50.2284),
                "description": "Major city in Eastern Province"
            },
            {
                "name": "Dhahran",
                "bbox": (26.2885, 50.1139, 26.3085, 50.1339),
                "description": "Oil industry hub"
            }
        ]

    async def should_seed_data(self, db: AsyncSession) -> bool:
        """Check if data should be seeded (if no OSM data exists)"""
        try:
            # Count places with OSM data source
            result = await db.execute(
                select(func.count(Place.id)).where(
                    Place.data_source == 'osm_overpass'
                )
            )
            osm_places_count = result.scalar_one()

            # If we have less than 100 OSM places, we should seed
            should_seed = osm_places_count < 100

            logger.info(
                f"OSM places count: {osm_places_count}, should seed: {should_seed}")
            return should_seed

        except Exception as e:
            logger.error(f"Error checking if should seed data: {e}")
            return False

    async def seed_saudi_cities(self, db: AsyncSession) -> dict:
        """Seed Saudi cities data from OSM Overpass"""
        logger.info("Starting automatic seeding of Saudi cities...")

        total_places_added = 0
        cities_seeded = []

        for city in self.saudi_cities:
            try:
                logger.info(f"Seeding {city['name']}...")

                # Extract bounding box
                min_lat, min_lon, max_lat, max_lon = city['bbox']

                # Seed from OSM Overpass
                places_added = await enhanced_place_data_service.seed_from_osm_overpass(
                    db, (min_lat, min_lon, max_lat, max_lon)
                )

                total_places_added += places_added
                cities_seeded.append({
                    "city": city['name'],
                    "places_added": places_added,
                    "bbox": city['bbox']
                })

                logger.info(f"✅ {city['name']}: {places_added} places added")

                # Small delay between cities to be respectful to OSM
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"❌ Failed to seed {city['name']}: {e}")
                cities_seeded.append({
                    "city": city['name'],
                    "places_added": 0,
                    "error": str(e)
                })

        logger.info(
            f"🎉 Seeding complete! Total places added: {total_places_added}")

        return {
            "total_places_added": total_places_added,
            "cities_seeded": cities_seeded,
            "status": "completed"
        }

    async def auto_seed_if_needed(self, db: AsyncSession) -> dict:
        """Automatically seed data if needed"""
        try:
            # Check if we should seed
            if not await self.should_seed_data(db):
                logger.info("✅ Data already seeded, skipping auto-seeding")
                return {
                    "status": "skipped",
                    "reason": "Data already exists",
                    "total_places_added": 0
                }

            # Perform seeding
            result = await self.seed_saudi_cities(db)
            return result

        except Exception as e:
            logger.error(f"❌ Auto-seeding failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "total_places_added": 0
            }

    async def get_seeding_status(self, db: AsyncSession) -> dict:
        """Get current seeding status and statistics"""
        try:
            # Count places by data source
            result = await db.execute(
                select(Place.data_source, func.count(Place.id))
                .group_by(Place.data_source)
            )
            source_distribution = dict(result.all())

            # Count total places
            total_result = await db.execute(select(func.count(Place.id)))
            total_places = total_result.scalar_one()

            # Check if data is seeded
            is_seeded = await self.should_seed_data(db)

            return {
                "is_seeded": not is_seeded,  # Inverted logic for clarity
                "total_places": total_places,
                "source_distribution": source_distribution,
                "saudi_cities_count": len(self.saudi_cities),
                "last_check": "auto-seeding service"
            }

        except Exception as e:
            logger.error(f"Error getting seeding status: {e}")
            return {
                "is_seeded": False,
                "error": str(e)
            }


# Global instance
auto_seeder_service = AutoSeederService()
