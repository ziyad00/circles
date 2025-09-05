#!/usr/bin/env python3
"""
OpenStreetMap Data Population Script
Populates missing data like photos, amenities, and other details from OSM
"""

from app.config import settings
from app.services.place_data_service_v2 import enhanced_place_data_service
from app.models import Place
from app.database import get_db
import sys
import os
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
import httpx
import logging

# Ensure project root on path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OSMDataPopulator:
    """Populates missing place data from OpenStreetMap"""

    def __init__(self):
        self.osm_base_url = "https://nominatim.openstreetmap.org"
        self.overpass_endpoints = settings.overpass_endpoints or [
            "https://overpass-api.de/api/interpreter"
        ]
        self.batch_size = 10
        self.delay_between_batches = 2  # seconds
        self.max_photos_per_place = 5

    async def populate_missing_data(self, db, limit: int = 100, city_filter: Optional[str] = None):
        """Populate missing data for places in database"""
        logger.info("Starting OSM data population...")

        # Get places with missing data
        places = await self._get_places_needing_data(db, limit, city_filter)

        if not places:
            logger.info("No places found that need data population")
            return {"places_processed": 0, "updated": 0}

        logger.info(f"Found {len(places)} places needing data population")

        total_updated = 0
        places_processed = 0

        # Process places in batches
        for i in range(0, len(places), self.batch_size):
            batch = places[i:i + self.batch_size]

            for place in batch:
                try:
                    updated = await self._populate_place_data(db, place)
                    if updated:
                        total_updated += 1
                    places_processed += 1
                    logger.info(
                        f"Processed {place.name} ({places_processed}/{len(places)})")

                except Exception as e:
                    logger.error(f"Failed to process {place.name}: {e}")
                    continue

            # Delay between batches to be respectful
            if i + self.batch_size < len(places):
                await asyncio.sleep(self.delay_between_batches)

        logger.info(
            f"Completed data population: {places_processed} processed, {total_updated} updated")
        return {
            "places_processed": places_processed,
            "updated": total_updated,
            "success_rate": total_updated / places_processed if places_processed > 0 else 0
        }

    async def _get_places_needing_data(self, db, limit: int, city_filter: Optional[str] = None) -> List[Place]:
        """Get places that need data population"""
        from sqlalchemy import select, or_, and_

        # Build query for places missing key data
        query = select(Place).where(
            or_(
                Place.website.is_(None),
                Place.phone.is_(None),
                Place.place_metadata.is_(None),
                and_(
                    Place.place_metadata.is_not(None),
                    Place.place_metadata.not_like('%amenities%')
                ),
                and_(
                    Place.place_metadata.is_not(None),
                    Place.place_metadata.not_like('%photos%')
                )
            )
        )

        if city_filter:
            query = query.where(Place.city.ilike(f"%{city_filter}%"))

        query = query.limit(limit)

        result = await db.execute(query)
        places = result.scalars().all()

        return list(places)

    async def _populate_place_data(self, db, place: Place) -> bool:
        """Populate data for a single place"""
        updated = False

        try:
            # Get OSM data for this place
            osm_data = await self._get_osm_data_for_place(place)

            if not osm_data:
                return False

            # Update place with OSM data
            if await self._update_place_with_osm_data(db, place, osm_data):
                updated = True

            # Try to get additional photos if we have coordinates
            if place.latitude and place.longitude:
                photos = await self._get_osm_photos_nearby(place.latitude, place.longitude, place.name)
                if photos:
                    if await self._update_place_photos(db, place, photos):
                        updated = True

        except Exception as e:
            logger.error(f"Error populating data for {place.name}: {e}")

        return updated

    async def _get_osm_data_for_place(self, place: Place) -> Optional[Dict[str, Any]]:
        """Get detailed OSM data for a place"""
        try:
            # First, try to find the OSM element ID
            osm_element = await self._find_osm_element(place)

            if not osm_element:
                return None

            # Get detailed data for the element
            detailed_data = await self._get_osm_element_details(osm_element)

            return detailed_data

        except Exception as e:
            logger.error(f"Error getting OSM data for {place.name}: {e}")
            return None

    async def _find_osm_element(self, place: Place) -> Optional[Dict[str, Any]]:
        """Find OSM element matching the place"""
        try:
            # Use Nominatim to search for the place
            params = {
                "q": place.name,
                "format": "json",
                "limit": 5,
                "addressdetails": 1,
                "extratags": 1
            }

            if place.city:
                params["city"] = place.city
            if place.latitude and place.longitude:
                params["viewbox"] = f"{place.longitude-0.01},{place.latitude-0.01},{place.longitude+0.01},{place.latitude+0.01}"

            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
                response = await client.get(
                    f"{self.osm_base_url}/search",
                    params=params,
                    headers={"User-Agent": "Circles-App/1.0"}
                )

                if response.status_code != 200:
                    return None

                results = response.json()

                if not results:
                    return None

                # Find the best match
                best_match = None
                best_score = 0

                for result in results:
                    score = self._calculate_match_score(place, result)
                    if score > best_score:
                        best_score = score
                        best_match = result

                return best_match if best_score > 0.6 else None

        except Exception as e:
            logger.error(f"Error finding OSM element for {place.name}: {e}")
            return None

    def _calculate_match_score(self, place: Place, osm_result: Dict[str, Any]) -> float:
        """Calculate how well an OSM result matches our place"""
        score = 0.0

        # Name similarity (40%)
        if 'display_name' in osm_result:
            from difflib import SequenceMatcher
            name_similarity = SequenceMatcher(
                None,
                place.name.lower(),
                osm_result['display_name'].split(',')[0].lower()
            ).ratio()
            score += 0.4 * name_similarity

        # Location proximity (40%)
        if place.latitude and place.longitude and 'lat' in osm_result and 'lon' in osm_result:
            try:
                osm_lat = float(osm_result['lat'])
                osm_lon = float(osm_result['lon'])

                # Simple distance calculation (rough approximation)
                distance = ((place.latitude - osm_lat) ** 2 +
                            (place.longitude - osm_lon) ** 2) ** 0.5
                # Closer = higher score
                proximity_score = max(0, 1 - distance * 100)
                score += 0.4 * proximity_score
            except (ValueError, TypeError):
                pass

        # Type/category match (20%)
        if 'type' in osm_result and place.categories:
            osm_type = osm_result['type']
            place_cats = place.categories.lower()

            if osm_type in ['restaurant', 'cafe', 'bar'] and 'restaurant' in place_cats:
                score += 0.2
            elif osm_type in ['shop', 'mall'] and 'shop' in place_cats:
                score += 0.2
            elif osm_type == 'hotel' and 'hotel' in place_cats:
                score += 0.2

        return score

    async def _get_osm_element_details(self, osm_element: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get detailed OSM data for an element"""
        try:
            # Build Overpass query to get element details
            element_type = osm_element.get('osm_type', 'node')
            element_id = osm_element.get('osm_id')

            if not element_id:
                return None

            query = f"""
            [out:json][timeout:10];
            {element_type}({element_id});
            out meta;
            """

            # Try different Overpass endpoints
            for endpoint in self.overpass_endpoints:
                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
                        response = await client.post(
                            endpoint,
                            data=query,
                            headers={"User-Agent": "Circles-App/1.0"}
                        )

                        if response.status_code == 200:
                            data = response.json()
                            elements = data.get('elements', [])

                            if elements:
                                element = elements[0]
                                return self._parse_osm_element_detailed(element)

                except Exception as e:
                    logger.warning(f"Failed to query {endpoint}: {e}")
                    continue

            return None

        except Exception as e:
            logger.error(f"Error getting OSM element details: {e}")
            return None

    def _parse_osm_element_detailed(self, element: Dict[str, Any]) -> Dict[str, Any]:
        """Parse detailed OSM element data"""
        tags = element.get('tags', {})

        result = {
            'osm_id': element.get('id'),
            'osm_type': element.get('type'),
            'tags': tags,
        }

        # Extract useful information
        if 'website' in tags:
            result['website'] = tags['website']
        if 'phone' in tags:
            result['phone'] = tags['phone']
        if 'opening_hours' in tags:
            result['opening_hours'] = tags['opening_hours']
        if 'wheelchair' in tags:
            result['wheelchair_accessible'] = tags['wheelchair'].lower() == 'yes'
        if 'wifi' in tags:
            result['wifi'] = tags['wifi'].lower() in ['yes', 'free']
        if 'outdoor_seating' in tags:
            result['outdoor_seating'] = tags['outdoor_seating'].lower() == 'yes'

        # Extract amenities
        amenities = {}
        amenity_mappings = {
            'wheelchair': 'wheelchair_accessible',
            'wifi': 'wifi',
            'outdoor_seating': 'outdoor_seating',
            'internet_access': 'internet_access',
            'delivery': 'delivery',
            'takeaway': 'takeout',
            'drive_through': 'drive_through',
            'reservation': 'reservations'
        }

        for osm_key, our_key in amenity_mappings.items():
            if osm_key in tags:
                value = tags[osm_key].lower()
                if value in ['yes', 'true', '1', 'free', 'designated']:
                    amenities[our_key] = True
                elif value in ['no', 'false', '0', 'none']:
                    amenities[our_key] = False

        if amenities:
            result['amenities'] = amenities

        return result

    async def _get_osm_photos_nearby(self, lat: float, lon: float, place_name: str) -> List[Dict[str, Any]]:
        """Get photos from various sources nearby"""
        photos = []

        try:
            # Try multiple photo sources

            # 1. Wikimedia Commons photos
            wikimedia_photos = await self._get_wikimedia_photos(lat, lon, place_name)
            photos.extend(wikimedia_photos)

            # 2. Flickr photos (if API key available)
            flickr_photos = await self._get_flickr_photos(lat, lon, place_name)
            photos.extend(flickr_photos)

            # 3. Foursquare photos (if API key available)
            if settings.foursquare_api_key and settings.foursquare_api_key != "demo_key_for_testing":
                fsq_photos = await self._get_foursquare_photos_nearby(lat, lon, place_name)
                photos.extend(fsq_photos)

            # 4. Fallback to placeholder if no real photos found
            if not photos:
                photos = await self._get_placeholder_photos(place_name)

            return photos[:self.max_photos_per_place]

        except Exception as e:
            logger.error(f"Error getting photos for {place_name}: {e}")
            return []

    async def _get_wikimedia_photos(self, lat: float, lon: float, place_name: str) -> List[Dict[str, Any]]:
        """Get photos from Wikimedia Commons"""
        try:
            # Search for images related to the place name
            search_url = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": place_name,
                "srnamespace": "6",  # File namespace
                "srlimit": "5",
                "srinfo": "",
                "srprop": ""
            }

            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
                response = await client.get(search_url, params=params)
                if response.status_code != 200:
                    return []

                data = response.json()
                search_results = data.get('query', {}).get('search', [])

                photos = []
                for result in search_results:
                    title = result.get('title', '')
                    if title.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        # Get image info
                        image_info = await self._get_wikimedia_image_info(title)
                        if image_info:
                            photos.append({
                                'url': image_info['url'],
                                'source': 'wikimedia_commons',
                                'width': image_info.get('width'),
                                'height': image_info.get('height'),
                                'caption': title,
                                'license': 'CC BY-SA'
                            })

                return photos

        except Exception as e:
            logger.warning(f"Wikimedia photo fetch failed: {e}")
            return []

    async def _get_wikimedia_image_info(self, title: str) -> Optional[Dict[str, Any]]:
        """Get detailed info for a Wikimedia image"""
        try:
            url = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url|size|mime",
                "iiurlwidth": "800"
            }

            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
                response = await client.get(url, params=params)
                if response.status_code != 200:
                    return None

                data = response.json()
                pages = data.get('query', {}).get('pages', {})
                page = list(pages.values())[0] if pages else None

                if page and 'imageinfo' in page:
                    info = page['imageinfo'][0]
                    return {
                        'url': info.get('url'),
                        'width': info.get('width'),
                        'height': info.get('height'),
                        'mime': info.get('mime')
                    }

                return None

        except Exception as e:
            logger.warning(f"Wikimedia image info fetch failed: {e}")
            return None

    async def _get_flickr_photos(self, lat: float, lon: float, place_name: str) -> List[Dict[str, Any]]:
        """Get photos from Flickr"""
        try:
            # Flickr API requires API key - for now, return empty
            # In production, you'd implement Flickr API integration
            return []

        except Exception as e:
            logger.warning(f"Flickr photo fetch failed: {e}")
            return []

    async def _get_foursquare_photos_nearby(self, lat: float, lon: float, place_name: str) -> List[Dict[str, Any]]:
        """Get photos from Foursquare API"""
        try:
            # This would use the existing Foursquare integration
            # For now, we'll skip this as it requires API setup
            return []

        except Exception as e:
            logger.warning(f"Foursquare photo fetch failed: {e}")
            return []

    async def _get_placeholder_photos(self, place_name: str) -> List[Dict[str, Any]]:
        """Get placeholder photos when no real photos are available"""
        try:
            # Create themed placeholder photos
            search_terms = place_name.replace(" ", ",").lower()

            photos = []
            for i in range(min(3, self.max_photos_per_place)):
                photo = {
                    'url': f'https://source.unsplash.com/random/800x600/?{search_terms}',
                    'source': 'unsplash_placeholder',
                    'width': 800,
                    'height': 600,
                    'caption': f'Photo of {place_name}',
                    'license': 'Unsplash'
                }
                photos.append(photo)

            return photos

        except Exception as e:
            logger.warning(f"Placeholder photo generation failed: {e}")
            return []

    async def _update_place_with_osm_data(self, db, place: Place, osm_data: Dict[str, Any]) -> bool:
        """Update place with OSM data"""
        updated = False

        # Update basic fields
        if 'website' in osm_data and not place.website:
            place.website = osm_data['website']
            updated = True

        if 'phone' in osm_data and not place.phone:
            place.phone = osm_data['phone']
            updated = True

        # Update metadata
        metadata = place.place_metadata or {}

        if 'opening_hours' in osm_data:
            metadata['opening_hours'] = osm_data['opening_hours']
            updated = True

        if 'amenities' in osm_data:
            metadata['amenities'] = osm_data['amenities']
            updated = True

        if 'tags' in osm_data:
            metadata['osm_tags'] = osm_data['tags']
            updated = True

        if updated:
            place.place_metadata = metadata
            place.last_enriched_at = datetime.now(timezone.utc)

        return updated

    async def _update_place_photos(self, db, place: Place, photos: List[Dict[str, Any]]) -> bool:
        """Update place with photos"""
        if not photos:
            return False

        metadata = place.place_metadata or {}
        existing_photos = metadata.get('photos', [])

        # Add new photos
        for photo in photos[:self.max_photos_per_place]:
            if photo not in existing_photos:
                existing_photos.append(photo)

        metadata['photos'] = existing_photos
        place.place_metadata = metadata

        return True


async def populate_osm_data(limit: int = 100, city_filter: Optional[str] = None):
    """Main function to populate OSM data"""
    logger.info(
        f"Starting OSM data population (limit: {limit}, city: {city_filter or 'all'})")

    populator = OSMDataPopulator()

    try:
        async for db in get_db():
            result = await populator.populate_missing_data(db, limit, city_filter)
            await db.commit()
            return result

    except Exception as e:
        logger.error(f"Failed to populate OSM data: {e}")
        return {"error": str(e)}


async def check_data_status():
    """Check current data status"""
    from sqlalchemy import select, func

    try:
        async for db in get_db():
            # Count places by data completeness
            total_result = await db.execute(select(func.count(Place.id)))
            total = total_result.scalar_one()

            with_website = await db.execute(
                select(func.count(Place.id)).where(Place.website.is_not(None))
            )
            website_count = with_website.scalar_one()

            with_phone = await db.execute(
                select(func.count(Place.id)).where(Place.phone.is_not(None))
            )
            phone_count = with_phone.scalar_one()

            with_metadata = await db.execute(
                select(func.count(Place.id)).where(
                    Place.place_metadata.is_not(None))
            )
            metadata_count = with_metadata.scalar_one()

            print("📊 Current Data Status:")
            print(f"   Total places: {total}")
            print(
                f"   With website: {website_count} ({website_count/total*100:.1f}%)")
            print(
                f"   With phone: {phone_count} ({phone_count/total*100:.1f}%)")
            print(
                f"   With metadata: {metadata_count} ({metadata_count/total*100:.1f}%)")

            return {
                "total": total,
                "website_count": website_count,
                "phone_count": phone_count,
                "metadata_count": metadata_count
            }

    except Exception as e:
        print(f"❌ Error checking data status: {e}")
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Populate missing OSM data")
    parser.add_argument("--limit", type=int, default=50,
                        help="Number of places to process")
    parser.add_argument("--city", type=str, help="Filter by city name")
    parser.add_argument("--status", action="store_true",
                        help="Check current data status only")

    args = parser.parse_args()

    if args.status:
        asyncio.run(check_data_status())
    else:
        result = asyncio.run(populate_osm_data(args.limit, args.city))
        print("\n🎉 Population Complete!")
        print(f"   Places processed: {result.get('places_processed', 0)}")
        print(f"   Places updated: {result.get('updated', 0)}")
        print(f"   Success rate: {result.get('success_rate', 0)*100:.1f}%")
