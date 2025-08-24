"""
Auto Seeder Service
Automatically seeds Saudi cities data when server starts (if not already seeded)
"""

import asyncio
import logging
from typing import List, Tuple, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from ..models import Place
from ..services.place_data_service_v2 import enhanced_place_data_service

logger = logging.getLogger(__name__)


class AutoSeederService:
    """Service for automatic seeding of Saudi cities data"""

    def __init__(self):
        self.saudi_cities = [
            # Major Cities - Riyadh Region
            {
                "name": "Riyadh",
                "bbox": (24.6136, 46.5753, 24.8336, 46.7953),
                "description": "Capital city of Saudi Arabia"
            },
            {
                "name": "Al-Kharj",
                "bbox": (24.1553, 47.3053, 24.1753, 47.3253),
                "description": "Agricultural city in Riyadh Province"
            },
            {
                "name": "Al-Diriyah",
                "bbox": (24.7336, 46.5753, 24.7536, 46.5953),
                "description": "Historic city and UNESCO World Heritage site"
            },
            {
                "name": "Al-Uyaynah",
                "bbox": (24.9083, 46.4083, 24.9283, 46.4283),
                "description": "Historic city near Riyadh"
            },
            {
                "name": "Al-Majma'ah",
                "bbox": (25.8583, 45.3583, 25.8783, 45.3783),
                "description": "City in Riyadh Province"
            },
            {
                "name": "Al-Zulfi",
                "bbox": (26.3083, 44.8083, 26.3283, 44.8283),
                "description": "City in Riyadh Province"
            },
            {
                "name": "Al-Ghat",
                "bbox": (26.1583, 44.9583, 26.1783, 44.9783),
                "description": "City in Riyadh Province"
            },
            {
                "name": "Al-Dawadmi",
                "bbox": (24.5083, 44.4083, 24.5283, 44.4283),
                "description": "City in Riyadh Province"
            },
            {
                "name": "Al-Aflaj",
                "bbox": (22.3083, 46.7083, 22.3283, 46.7283),
                "description": "City in Riyadh Province"
            },
            {
                "name": "Al-Hareeq",
                "bbox": (24.8083, 46.8083, 24.8283, 46.8283),
                "description": "City in Riyadh Province"
            },
            {
                "name": "Al-Hotat Bani Tamim",
                "bbox": (23.6583, 46.7583, 23.6783, 46.7783),
                "description": "City in Riyadh Province"
            },

            # Western Region - Makkah Province
            {
                "name": "Jeddah",
                "bbox": (21.3858, 39.0925, 21.6058, 39.3125),
                "description": "Major port city on the Red Sea"
            },
            {
                "name": "Mecca",
                "bbox": (21.3225, 39.7262, 21.5225, 39.9262),
                "description": "Holy city and religious capital"
            },
            {
                "name": "Taif",
                "bbox": (21.1703, 40.3158, 21.3903, 40.5358),
                "description": "Mountain resort city"
            },
            {
                "name": "Rabigh",
                "bbox": (22.7986, 38.9986, 22.8186, 39.0186),
                "description": "Coastal city in Makkah Province"
            },
            {
                "name": "Al-Qunfudhah",
                "bbox": (19.1083, 41.0583, 19.1283, 41.0783),
                "description": "Coastal city in Makkah Province"
            },
            {
                "name": "Al-Lith",
                "bbox": (20.1583, 40.2583, 20.1783, 40.2783),
                "description": "Coastal city in Makkah Province"
            },

            # Western Region - Madinah Province
            {
                "name": "Medina",
                "bbox": (24.4247, 39.4692, 24.6447, 39.6892),
                "description": "Second holiest city in Islam"
            },
            {
                "name": "Yanbu",
                "bbox": (24.0883, 38.0583, 24.1083, 38.0783),
                "description": "Industrial port city"
            },
            {
                "name": "Al-Ula",
                "bbox": (26.6083, 37.9083, 26.6283, 37.9283),
                "description": "Historic city and tourist destination"
            },

            # Eastern Province
            {
                "name": "Dammam",
                "bbox": (26.3207, 49.9888, 26.5207, 50.1888),
                "description": "Capital of Eastern Province"
            },
            {
                "name": "Al-Khobar",
                "bbox": (26.1795, 50.1084, 26.3995, 50.3284),
                "description": "Major city in Eastern Province"
            },
            {
                "name": "Dhahran",
                "bbox": (26.1885, 50.0139, 26.4085, 50.2339),
                "description": "Oil industry hub"
            },
            {
                "name": "Al-Ahsa",
                "bbox": (25.3833, 49.5833, 25.4033, 49.6033),
                "description": "Oasis city and UNESCO World Heritage site"
            },
            {
                "name": "Al-Jubail",
                "bbox": (27.0083, 49.6583, 27.0283, 49.6783),
                "description": "Industrial city and port"
            },
            {
                "name": "Ras Tanura",
                "bbox": (26.7083, 50.1583, 26.7283, 50.1783),
                "description": "Oil port city"
            },
            {
                "name": "Al-Qatif",
                "bbox": (26.5583, 49.9983, 26.5783, 50.0183),
                "description": "Historic coastal city"
            },

            # Southern Region - Asir Province
            {
                "name": "Abha",
                "bbox": (18.1164, 42.4053, 18.3364, 42.6253),
                "description": "Capital of Asir Province"
            },
            {
                "name": "Khamis Mushait",
                "bbox": (18.3083, 42.7083, 18.3283, 42.7283),
                "description": "Military and commercial city"
            },
            {
                "name": "Al-Baha",
                "bbox": (20.0083, 41.4583, 20.0283, 41.4783),
                "description": "Capital of Al-Baha Province"
            },
            {
                "name": "Jizan",
                "bbox": (16.9083, 42.5583, 16.9283, 42.5783),
                "description": "Capital of Jizan Province"
            },
            {
                "name": "Najran",
                "bbox": (17.5083, 44.1583, 17.5283, 44.1783),
                "description": "Capital of Najran Province"
            },
            {
                "name": "Al-Ranyah",
                "bbox": (21.2083, 42.7083, 21.2283, 42.7283),
                "description": "City in Asir Province"
            },
            {
                "name": "Al-Namas",
                "bbox": (19.1583, 42.1083, 19.1783, 42.1283),
                "description": "City in Asir Province"
            },

            # Northern Region - Tabuk Province
            {
                "name": "Tabuk",
                "bbox": (28.2835, 36.4664, 28.5035, 36.6864),
                "description": "Capital of Tabuk Province"
            },
            {
                "name": "Al-Wajh",
                "bbox": (26.2083, 36.4583, 26.2283, 36.4783),
                "description": "Coastal city in Tabuk Province"
            },
            {
                "name": "Duba",
                "bbox": (27.3583, 35.7083, 27.3783, 35.7283),
                "description": "Port city in Tabuk Province"
            },
            {
                "name": "Haql",
                "bbox": (29.2583, 34.9083, 29.2783, 34.9283),
                "description": "Border city near Jordan"
            },

            # Central Region - Qassim Province
            {
                "name": "Buraydah",
                "bbox": (26.3583, 43.9583, 26.3783, 43.9783),
                "description": "Capital of Qassim Province"
            },
            {
                "name": "Unaizah",
                "bbox": (26.1083, 43.9083, 26.1283, 43.9283),
                "description": "Major city in Qassim Province"
            },
            {
                "name": "Al-Rass",
                "bbox": (25.8583, 43.5083, 25.8783, 43.5283),
                "description": "Agricultural city in Qassim"
            },

            # Central Region - Ha'il Province
            {
                "name": "Ha'il",
                "bbox": (27.5083, 41.7083, 27.5283, 41.7283),
                "description": "Capital of Ha'il Province"
            },
            {
                "name": "Al-Jouf",
                "bbox": (29.9583, 40.2083, 29.9783, 40.2283),
                "description": "Capital of Al-Jouf Province"
            },

            # Additional Major Cities (Alternative Names)
            {
                "name": "Al-Khamis Mushait",
                "bbox": (18.3083, 42.7083, 18.3283, 42.7283),
                "description": "Alternative spelling for Khamis Mushait"
            },
            {
                "name": "Al-Bahah",
                "bbox": (20.0083, 41.4583, 20.0283, 41.4783),
                "description": "Alternative spelling for Al-Baha"
            },
            {
                "name": "Sakaka",
                "bbox": (29.9583, 40.2083, 29.9783, 40.2283),
                "description": "Alternative name for Al-Jouf"
            },
            {
                "name": "Al-Taif",
                "bbox": (21.2703, 40.4158, 21.2903, 40.4358),
                "description": "Alternative spelling for Taif"
            },
            {
                "name": "Al-Hariq",
                "bbox": (24.8083, 46.8083, 24.8283, 46.8283),
                "description": "Alternative spelling for Al-Hareeq"
            },
            {
                "name": "Al-Hotah",
                "bbox": (23.6583, 46.7583, 23.6783, 46.7783),
                "description": "Alternative spelling for Al-Hotat Bani Tamim"
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

            # If we have less than 500 OSM places, we should seed (increased for more cities)
            should_seed = osm_places_count < 500

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

                # Seed from OSM Overpass (without transaction management)
                places_added = await self._seed_city_from_osm(
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

    async def _seed_city_from_osm(self, db: AsyncSession, bbox: Tuple[float, float, float, float]) -> int:
        """Seed a single city from OSM without transaction management"""
        try:
            # Build Overpass query
            query = enhanced_place_data_service._build_overpass_query(bbox)

            # Fetch data from Overpass
            places_data = await enhanced_place_data_service._fetch_overpass_data(query)

            # Process and save to database
            seeded_count = 0
            for place_data in places_data:
                try:
                    # Create place without flush to avoid transaction issues
                    place = await self._create_place_safe(db, place_data)
                    if place:
                        seeded_count += 1
                        # Commit after each successful place creation
                        await db.commit()
                except Exception as e:
                    logger.warning(
                        f"Failed to create place from OSM data: {e}")
                    # Rollback on error and continue
                    await db.rollback()

            logger.info(f"Seeded {seeded_count} places from OSM Overpass")
            return seeded_count

        except Exception as e:
            logger.error(f"Failed to seed from OSM Overpass: {e}")
            raise

    async def _create_place_safe(self, db: AsyncSession, place_data: Dict[str, Any]) -> Optional[Place]:
        """Create place from OSM data with safe transaction handling"""
        # Validate place data
        if not enhanced_place_data_service._validate_place_data(place_data):
            logger.warning(
                f"Invalid place data: {place_data.get('name', 'Unknown')}")
            return None

        # Check if place already exists
        existing = await db.execute(
            select(Place).where(
                and_(
                    Place.external_id == place_data['external_id'],
                    Place.data_source == 'osm_overpass'
                )
            )
        )
        if existing.scalar_one_or_none():
            return None

        # Create new place
        place = Place(
            name=place_data['name'],
            latitude=place_data['latitude'],
            longitude=place_data['longitude'],
            categories=place_data['categories'],
            address=place_data.get('address'),
            city=place_data.get('city'),
            phone=place_data.get('phone'),
            website=place_data.get('website'),
            external_id=place_data['external_id'],
            data_source='osm_overpass',
            place_metadata={
                'opening_hours': place_data.get('opening_hours'),
                'osm_tags': place_data.get('osm_tags', {})
            }
        )

        db.add(place)
        return place

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
