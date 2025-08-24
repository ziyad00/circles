"""
Enhanced Place Data Service - OSM Overpass + Foursquare Enrichment
"""

import httpx
import asyncio
import json
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import logging

from ..models import Place
from ..config import settings
from ..utils import haversine_distance

logger = logging.getLogger(__name__)


class EnhancedPlaceDataService:
    """Enhanced place data service with OSM Overpass seeding and Foursquare enrichment"""

    def __init__(self):
        self.foursquare_api_key = getattr(settings, 'foursquare_api_key', None)
        self.enrichment_ttl_hot = 14  # days for hot places
        self.enrichment_ttl_cold = 60  # days for other places
        self.max_enrichment_distance = 150  # meters
        self.min_name_similarity = 0.65

        # OSM tags to seed
        self.osm_seed_tags = {
            'amenity': ['cafe', 'restaurant', 'fast_food', 'bank', 'atm', 'pharmacy',
                        'hospital', 'school', 'university', 'fuel'],
            'shop': ['supermarket', 'mall'],
            'leisure': ['park', 'fitness_centre']
        }

    async def seed_from_osm_overpass(self, db: AsyncSession, bbox: Tuple[float, float, float, float]):
        """
        Seed places from OpenStreetMap Overpass API

        Args:
            db: Database session
            bbox: (min_lat, min_lon, max_lat, max_lon) bounding box
        """
        try:
            # Build Overpass query
            query = self._build_overpass_query(bbox)

            # Fetch data from Overpass
            places_data = await self._fetch_overpass_data(query)

            # Process and save to database
            seeded_count = 0
            for place_data in places_data:
                try:
                    place = await self._create_place_from_osm(db, place_data)
                    if place:
                        seeded_count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to create place from OSM data: {e}")

            await db.commit()
            logger.info(f"Seeded {seeded_count} places from OSM Overpass")
            return seeded_count

        except Exception as e:
            logger.error(f"Failed to seed from OSM Overpass: {e}")
            await db.rollback()
            raise

    async def enrich_place_if_needed(self, place: Place, db: AsyncSession) -> bool:
        """
        Enrich place data from Foursquare if needed

        Args:
            place: Place to enrich
            db: Database session

        Returns:
            True if enriched, False if not needed
        """
        if not self.foursquare_api_key or self.foursquare_api_key == "demo_key_for_testing":
            logger.warning(
                "Foursquare API key not configured or using demo key")
            return False

        # Check if enrichment is needed
        if not self._needs_enrichment(place):
            return False

        # Retry logic with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Search for matching Foursquare venue
                fsq_venue = await self._find_foursquare_venue(place)
                if not fsq_venue:
                    logger.info(
                        f"No Foursquare venue found for place {place.id}")
                    return False

                # Get detailed venue information
                venue_details = await self._get_foursquare_venue_details(fsq_venue['fsq_id'])
                if not venue_details:
                    return False

                # Get venue photos
                photos = await self._get_foursquare_venue_photos(fsq_venue['fsq_id'])

                # Update place with enriched data
                await self._update_place_with_foursquare_data(
                    place, venue_details, photos, fsq_venue, db
                )

                await db.commit()
                logger.info(f"Enriched place {place.id} with Foursquare data")
                return True

            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1} failed to enrich place {place.id}: {e}")
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to enrich place {place.id} after {max_retries} attempts")
                    await db.rollback()
                    return False
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        return False

    async def search_places_with_enrichment(
        self,
        lat: float,
        lon: float,
        radius: int = 5000,
        query: Optional[str] = None,
        limit: int = 20,
        db: AsyncSession = None
    ) -> List[Dict[str, Any]]:
        """
        Search places with automatic enrichment and Foursquare discovery fallback

        Args:
            lat: Latitude
            lon: Longitude
            radius: Search radius in meters
            query: Optional search query
            limit: Maximum results
            db: Database session

        Returns:
            List of places with enrichment applied, including Foursquare-only places
        """
        if not db:
            raise ValueError("Database session required")

        start_time = datetime.now()

        try:
            # Search places in database
            places = await self._search_places_in_db(lat, lon, radius, query, limit, db)

            # Enrich places that need it
            enriched_count = 0
            for place in places:
                if await self.enrich_place_if_needed(place, db):
                    enriched_count += 1

            # Convert to response format
            result = []
            for place in places:
                place_dict = self._place_to_dict(place)
                place_dict['quality_score'] = self._calculate_quality_score(
                    place)
                result.append(place_dict)

            # If we have fewer results than requested and have a query, try Foursquare discovery
            if len(result) < limit and query and self.foursquare_api_key and self.foursquare_api_key != "demo_key_for_testing":
                logger.info(
                    f"Found {len(result)} places in DB, trying Foursquare discovery for '{query}'")
                foursquare_places = await self._discover_foursquare_places(lat, lon, radius, query, limit - len(result), db)
                result.extend(foursquare_places)

            # Sort by ranking score
            result.sort(key=lambda x: self._calculate_ranking_score(
                x, lat, lon, query), reverse=True)

            # Track performance metrics
            query_time_ms = (datetime.now() -
                             start_time).total_seconds() * 1000
            from ..services.place_metrics_service import place_metrics_service
            await place_metrics_service.track_search_performance(query_time_ms, len(result))

            logger.info(
                f"Found {len(result)} places (DB: {len(places)}, FSQ: {len(result) - len(places)}), enriched {enriched_count} in {query_time_ms:.2f}ms")
            return result

        except Exception as e:
            logger.error(f"Failed to search places with enrichment: {e}")
            return []

    def _build_overpass_query(self, bbox: Tuple[float, float, float, float]) -> str:
        """Build Overpass API query for seeding places"""
        min_lat, min_lon, max_lat, max_lon = bbox

        # Build tag filters
        tag_filters = []
        for category, tags in self.osm_seed_tags.items():
            for tag in tags:
                tag_filters.append(
                    f'node["{category}"="{tag}"]({min_lat},{min_lon},{max_lat},{max_lon});')
                tag_filters.append(
                    f'way["{category}"="{tag}"]({min_lat},{min_lon},{max_lat},{max_lon});')

        query = f"""
        [out:json][timeout:25];
        (
            {''.join(tag_filters)}
        );
        out center;
        """
        return query

    async def _fetch_overpass_data(self, query: str) -> List[Dict[str, Any]]:
        """Fetch data from Overpass API"""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.post(
                    "https://overpass-api.de/api/interpreter",
                    data=query,
                    timeout=30.0
                )

                # Handle different status codes
                if response.status_code == 200:
                    data = response.json()

                    places = []
                    for element in data.get('elements', []):
                        if element['type'] in ['node', 'way']:
                            place_data = self._parse_overpass_element(element)
                            if place_data:
                                places.append(place_data)

                    logger.info(
                        f"Fetched {len(places)} places from Overpass API")
                    return places
                elif response.status_code == 429:
                    logger.warning("Overpass API rate limit exceeded")
                    return []
                elif response.status_code >= 500:
                    logger.error(
                        f"Overpass API server error: {response.status_code}")
                    return []
                else:
                    logger.error(
                        f"Overpass API HTTP error: {response.status_code}")
                    return []

        except httpx.TimeoutException:
            logger.error("Overpass API request timed out")
            return []
        except httpx.RequestError as e:
            logger.error(f"Overpass API request error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in Overpass API: {e}")
            return []

    def _parse_overpass_element(self, element: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse Overpass element into place data"""
        try:
            tags = element.get('tags', {})

            # Get coordinates
            if element['type'] == 'node':
                lat = element.get('lat')
                lon = element.get('lon')
            else:  # way
                center = element.get('center', {})
                lat = center.get('lat')
                lon = center.get('lon')

            if not lat or not lon:
                return None

            # Get name and category
            name = tags.get('name') or tags.get(
                'brand') or tags.get('operator')
            if not name:
                return None

            # Determine category
            category = self._determine_category(tags)

            return {
                'name': name,
                'latitude': float(lat),
                'longitude': float(lon),
                'categories': category,
                'address': tags.get('addr:street'),
                'city': tags.get('addr:city'),
                'phone': tags.get('phone'),
                'website': tags.get('website'),
                'opening_hours': tags.get('opening_hours'),
                'external_id': f"osm_{element['type']}_{element['id']}",
                'data_source': 'osm_overpass'
            }

        except Exception as e:
            logger.warning(f"Failed to parse Overpass element: {e}")
            return None

    def _determine_category(self, tags: Dict[str, str]) -> str:
        """Determine place category from OSM tags"""
        if 'amenity' in tags:
            return f"amenity:{tags['amenity']}"
        elif 'shop' in tags:
            return f"shop:{tags['shop']}"
        elif 'leisure' in tags:
            return f"leisure:{tags['leisure']}"
        else:
            return "unknown"

    def _validate_place_data(self, place_data: Dict[str, Any]) -> bool:
        """Validate place data quality"""
        # Required fields
        required_fields = ['name', 'latitude', 'longitude', 'external_id']
        for field in required_fields:
            if not place_data.get(field):
                logger.warning(f"Missing required field: {field}")
                return False

        # Validate coordinates
        try:
            lat, lon = float(place_data['latitude']), float(
                place_data['longitude'])
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                logger.warning(f"Invalid coordinates: {lat}, {lon}")
                return False
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid coordinate format: {place_data.get('latitude')}, {place_data.get('longitude')}")
            return False

        # Validate name (not empty and reasonable length)
        name = place_data['name'].strip()
        if not name or len(name) > 200:
            logger.warning(f"Invalid name: '{name}'")
            return False

        return True

    async def _create_place_from_osm(self, db: AsyncSession, place_data: Dict[str, Any]) -> Optional[Place]:
        """Create place from OSM data"""
        # Validate place data
        if not self._validate_place_data(place_data):
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
            metadata={
                'opening_hours': place_data.get('opening_hours'),
                'osm_tags': place_data.get('osm_tags', {})
            }
        )

        db.add(place)
        await db.flush()
        return place

    def _needs_enrichment(self, place: Place) -> bool:
        """Check if place needs enrichment"""
        if not place.last_enriched_at:
            return True

        # Check TTL based on place activity
        ttl_days = self.enrichment_ttl_hot if self._is_hot_place(
            place) else self.enrichment_ttl_cold
        cutoff_date = datetime.now() - timedelta(days=ttl_days)

        return place.last_enriched_at < cutoff_date

    def _is_hot_place(self, place: Place) -> bool:
        """Determine if place is 'hot' (frequently visited)"""
        # This could be based on check-in frequency, ratings, etc.
        # For now, use a simple heuristic
        return place.rating and place.rating >= 4.0

    async def _find_foursquare_venue(self, place: Place) -> Optional[Dict[str, Any]]:
        """Find matching Foursquare venue for place"""
        if not self.foursquare_api_key:
            return None

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            # Search for venues near the place
            url = "https://api.foursquare.com/v3/places/search"
            headers = {
                "Authorization": self.foursquare_api_key,
                "Accept": "application/json"
            }
            params = {
                "ll": f"{place.latitude},{place.longitude}",
                "radius": self.max_enrichment_distance,
                "query": place.name,
                "limit": 10
            }

            try:
                response = await client.get(url, headers=headers, params=params)

                # Handle different status codes
                if response.status_code == 200:
                    pass  # Success
                elif response.status_code == 401:
                    logger.error(
                        "Foursquare API authentication failed - check API key")
                    return None
                elif response.status_code == 429:
                    logger.warning("Foursquare API rate limit exceeded")
                    return None
                elif response.status_code >= 500:
                    logger.error(
                        f"Foursquare API server error: {response.status_code}")
                    return None
                else:
                    logger.error(
                        f"Foursquare API request failed: {response.status_code}")
                    return None

            except httpx.TimeoutException:
                logger.error("Foursquare API request timed out")
                return None
            except httpx.RequestError as e:
                logger.error(f"Foursquare API request error: {e}")
                return None

            data = response.json()
            venues = data.get('results', [])

            # Find best match
            best_match = None
            best_score = 0

            for venue in venues:
                score = self._calculate_match_score(place, venue)
                if score > best_score and score >= self.min_name_similarity:
                    best_score = score
                    best_match = venue

            if best_match:
                return {
                    'fsq_id': best_match['fsq_id'],
                    'name': best_match['name'],
                    'match_score': best_score,
                    'distance': best_match.get('distance', 0)
                }

            return None

    def _calculate_match_score(self, place: Place, venue: Dict[str, Any]) -> float:
        """Calculate match score between place and Foursquare venue"""
        # Name similarity
        name_similarity = SequenceMatcher(
            None, place.name.lower(), venue['name'].lower()).ratio()

        # Distance score (closer is better)
        distance = venue.get('distance', 0)
        distance_score = max(0, 1 - (distance / self.max_enrichment_distance))

        # Category match
        category_score = 0.5  # Default
        if venue.get('categories'):
            venue_categories = [cat['name'].lower()
                                for cat in venue['categories']]
            place_categories = place.categories.lower().split(',') if place.categories else []

            for pc in place_categories:
                for vc in venue_categories:
                    if pc.strip() in vc or vc in pc.strip():
                        category_score = 1.0
                        break

        # Weighted score
        return 0.6 * name_similarity + 0.3 * distance_score + 0.1 * category_score

    async def _get_foursquare_venue_details(self, fsq_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed venue information from Foursquare"""
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            url = f"https://api.foursquare.com/v3/places/{fsq_id}"
            headers = {
                "Authorization": self.foursquare_api_key,
                "Accept": "application/json"
            }
            params = {
                "fields": "fsq_id,name,tel,website,hours,rating,price,stats,categories,location"
            }

            try:
                response = await client.get(url, headers=headers, params=params)

                # Handle different status codes
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    logger.error(
                        "Foursquare API authentication failed - check API key")
                    return None
                elif response.status_code == 429:
                    logger.warning("Foursquare API rate limit exceeded")
                    return None
                elif response.status_code >= 500:
                    logger.error(
                        f"Foursquare API server error: {response.status_code}")
                    return None
                else:
                    logger.error(
                        f"Foursquare API request failed: {response.status_code}")
                    return None

            except httpx.TimeoutException:
                logger.error("Foursquare API request timed out")
                return None
            except httpx.RequestError as e:
                logger.error(f"Foursquare API request error: {e}")
                return None

    async def _get_foursquare_venue_photos(self, fsq_id: str) -> List[Dict[str, Any]]:
        """Get venue photos from Foursquare"""
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            url = f"https://api.foursquare.com/v3/places/{fsq_id}/photos"
            headers = {
                "Authorization": self.foursquare_api_key,
                "Accept": "application/json"
            }
            params = {"limit": 5}

            try:
                response = await client.get(url, headers=headers, params=params)

                # Handle different status codes
                if response.status_code == 200:
                    data = response.json()
                    # Foursquare photos endpoint returns a list directly, not a dict with 'results'
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict) and 'results' in data:
                        return data.get('results', [])
                    else:
                        logger.warning(
                            f"Unexpected photo response format: {type(data)}")
                        return []
                elif response.status_code == 401:
                    logger.error(
                        "Foursquare API authentication failed - check API key")
                    return []
                elif response.status_code == 429:
                    logger.warning("Foursquare API rate limit exceeded")
                    return []
                elif response.status_code >= 500:
                    logger.error(
                        f"Foursquare API server error: {response.status_code}")
                    return []
                else:
                    logger.error(
                        f"Foursquare API request failed: {response.status_code}")
                    return []

            except httpx.TimeoutException:
                logger.error("Foursquare API request timed out")
                return []
            except httpx.RequestError as e:
                logger.error(f"Foursquare API request error: {e}")
                return []

    async def _discover_foursquare_places(
        self,
        lat: float,
        lon: float,
        radius: int,
        query: str,
        limit: int,
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Discover places from Foursquare that don't exist in our database"""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                url = "https://api.foursquare.com/v3/places/search"
                headers = {
                    "Authorization": self.foursquare_api_key,
                    "Accept": "application/json"
                }
                params = {
                    "ll": f"{lat},{lon}",
                    "radius": radius,
                    "query": query,
                    "limit": limit * 2,  # Get more to filter out existing places
                    "fields": "fsq_id,name,tel,website,hours,rating,price,stats,categories,location"
                }

                try:
                    response = await client.get(url, headers=headers, params=params)

                    if response.status_code == 200:
                        data = response.json()
                        venues = data.get('results', [])

                        # Filter out venues that already exist in our database
                        new_venues = []
                        for venue in venues:
                            if not await self._venue_exists_in_db(venue, db):
                                new_venues.append(venue)

                        # Convert to place format
                        result = []
                        for venue in new_venues[:limit]:
                            place_dict = self._foursquare_venue_to_place_dict(
                                venue, lat, lon)
                            result.append(place_dict)

                        logger.info(
                            f"Discovered {len(result)} new places from Foursquare")
                        return result
                    else:
                        logger.warning(
                            f"Foursquare discovery failed: {response.status_code}")
                        return []

                except httpx.TimeoutException:
                    logger.error("Foursquare discovery request timed out")
                    return []
                except httpx.RequestError as e:
                    logger.error(f"Foursquare discovery request error: {e}")
                    return []

        except Exception as e:
            logger.error(f"Failed to discover Foursquare places: {e}")
            return []

    async def _venue_exists_in_db(self, venue: Dict[str, Any], db: AsyncSession) -> bool:
        """Check if a Foursquare venue already exists in our database"""
        try:
            # Check by Foursquare ID first
            if venue.get('fsq_id'):
                existing = await db.execute(
                    select(Place).where(Place.external_id == venue['fsq_id'])
                )
                if existing.scalar_one_or_none():
                    return True

            # Check by name and location (within 150m)
            venue_lat = venue.get('location', {}).get('latitude')
            venue_lon = venue.get('location', {}).get('longitude')
            venue_name = venue.get('name', '')

            if venue_lat and venue_lon and venue_name:
                # Find places within 150m with similar names
                places = await self._search_places_in_db(
                    venue_lat, venue_lon, 150, venue_name, 10, db
                )

                for place in places:
                    name_similarity = SequenceMatcher(
                        None, venue_name.lower(), place.name.lower()
                    ).ratio()
                    if name_similarity >= self.min_name_similarity:
                        return True

            return False

        except Exception as e:
            logger.error(f"Error checking if venue exists: {e}")
            return False

    def _foursquare_venue_to_place_dict(self, venue: Dict[str, Any], search_lat: float, search_lon: float) -> Dict[str, Any]:
        """Convert Foursquare venue to place dictionary format"""
        venue_lat = venue.get('location', {}).get('latitude', search_lat)
        venue_lon = venue.get('location', {}).get('longitude', search_lon)

        # Calculate distance from search location
        distance = haversine_distance(
            search_lat, search_lon, venue_lat, venue_lon)

        # Determine category
        categories = venue.get('categories', [])
        category_str = ','.join([cat.get('name', '')
                                for cat in categories]) if categories else 'unknown'

        return {
            'id': None,  # Not in database yet
            'name': venue.get('name', 'Unknown'),
            'latitude': venue_lat,
            'longitude': venue_lon,
            'categories': category_str,
            'rating': venue.get('rating'),
            'phone': venue.get('tel'),
            'website': venue.get('website'),
            'address': None,  # Foursquare doesn't provide detailed address
            'city': None,
            'external_id': venue.get('fsq_id'),
            'data_source': 'foursquare',
            'metadata': {
                'foursquare_id': venue.get('fsq_id'),
                'opening_hours': venue.get('hours', {}).get('display', ''),
                'price_level': venue.get('price'),
                'review_count': venue.get('stats', {}).get('total_ratings'),
                'photo_count': venue.get('stats', {}).get('total_photos'),
                'tip_count': venue.get('stats', {}).get('total_tips'),
                'distance_from_search': distance,
                'discovery_source': 'foursquare',
                'needs_promotion': True  # Flag to indicate this needs to be saved to DB
            },
            'last_enriched_at': None,
            'quality_score': self._calculate_quality_score_from_venue(venue)
        }

    def _calculate_quality_score_from_venue(self, venue: Dict[str, Any]) -> float:
        """Calculate quality score for a Foursquare venue"""
        score = 0.0

        # Phone (+0.3)
        if venue.get('tel'):
            score += 0.3

        # Hours (+0.3)
        if venue.get('hours', {}).get('display'):
            score += 0.3

        # Photos (+0.2)
        if venue.get('stats', {}).get('total_photos', 0) > 0:
            score += 0.2

        # Rating (+0.2)
        if venue.get('rating'):
            score += 0.2

        return min(score, 1.0)

    async def _update_place_with_foursquare_data(
        self,
        place: Place,
        venue_details: Dict[str, Any],
        photos: List[Dict[str, Any]],
        match_info: Dict[str, Any],
        db: AsyncSession
    ):
        """Update place with Foursquare data"""
        # Update basic fields
        place.phone = venue_details.get('tel') or place.phone
        place.website = venue_details.get('website') or place.website
        place.rating = venue_details.get('rating') or place.rating

        # Update metadata
        metadata = place.place_metadata or {}
        metadata.update({
            'opening_hours': venue_details.get('hours', {}).get('display', ''),
            'price_level': venue_details.get('price'),
            'review_count': venue_details.get('stats', {}).get('total_ratings'),
            'photo_count': venue_details.get('stats', {}).get('total_photos'),
            'tip_count': venue_details.get('stats', {}).get('total_tips'),
            'foursquare_id': venue_details.get('fsq_id'),
            'match_score': match_info['match_score'],
            'match_distance': match_info['distance'],
            'photos': [
                {
                    'url': photo.get('prefix') + 'original' + photo.get('suffix'),
                    'width': photo.get('width'),
                    'height': photo.get('height')
                }
                for photo in photos[:5]
            ],
            'last_enriched_at': datetime.now().isoformat(),
            'enrichment_source': 'foursquare'
        })

        place.place_metadata = metadata
        place.last_enriched_at = datetime.now()

    def _calculate_quality_score(self, place: Place) -> float:
        """Calculate quality score for place"""
        score = 0.0

        # Phone (+0.3)
        if place.phone:
            score += 0.3

        # Hours (+0.3)
        if hasattr(place, 'place_metadata') and place.place_metadata and isinstance(place.place_metadata, dict) and place.place_metadata.get('opening_hours'):
            score += 0.3

        # Photos (+0.2)
        if hasattr(place, 'place_metadata') and place.place_metadata and isinstance(place.place_metadata, dict) and place.place_metadata.get('photos'):
            score += 0.2

        # Recently enriched (+0.2)
        if place.last_enriched_at:
            days_since_enrichment = (
                datetime.now() - place.last_enriched_at).days
            if days_since_enrichment < 14:
                score += 0.2

        return min(score, 1.0)

    def _calculate_ranking_score(self, place_dict: Dict[str, Any], lat: float, lon: float, query: Optional[str]) -> float:
        """Calculate ranking score for place"""
        # Distance score (45%)
        distance = haversine_distance(
            lat, lon, place_dict['latitude'], place_dict['longitude'])
        distance_score = max(0, 1 - (distance / 5000))  # Normalize to 5km

        # Text match score (25%)
        text_match_score = 0.5  # Default
        if query:
            name_similarity = SequenceMatcher(
                None, query.lower(), place_dict['name'].lower()).ratio()
            text_match_score = name_similarity

        # Category boost (15%)
        category_boost = 0.5  # Default
        if query and place_dict.get('categories'):
            query_lower = query.lower()
            categories = place_dict['categories'].lower()
            if query_lower in categories or any(cat in query_lower for cat in categories.split(',')):
                category_boost = 1.0

        # Quality score (15%)
        quality_score = place_dict.get('quality_score', 0.0)

        return (0.45 * distance_score +
                0.25 * text_match_score +
                0.15 * category_boost +
                0.15 * quality_score)

    async def _search_places_in_db(
        self,
        lat: float,
        lon: float,
        radius: int,
        query: Optional[str] = None,
        limit: int = 20,
        db: AsyncSession = None
    ) -> List[Place]:
        """Search places in database within radius using PostGIS for better performance"""
        if not db:
            raise ValueError("Database session required")

        # Use PostGIS spatial query if available
        from ..config import settings
        if settings.use_postgis:
            return await self._search_places_with_postgis(lat, lon, radius, query, limit, db)
        else:
            return await self._search_places_with_bounding_box(lat, lon, radius, query, limit, db)

    async def _search_places_with_postgis(
        self,
        lat: float,
        lon: float,
        radius: int,
        query: Optional[str] = None,
        limit: int = 20,
        db: AsyncSession = None
    ) -> List[Place]:
        """Search places using PostGIS spatial queries"""
        from sqlalchemy import text

        # Build the query with spatial distance calculation
        sql = """
        SELECT p.*, ST_Distance(p.location, ST_Point(:lon, :lat)::geography) as distance
        FROM places p
        WHERE p.location IS NOT NULL
        AND ST_DWithin(p.location, ST_Point(:lon, :lat)::geography, :radius)
        """

        params = {
            'lat': lat,
            'lon': lon,
            'radius': radius
        }

        # Add text search if provided
        if query:
            sql += " AND (p.name ILIKE :query OR p.categories ILIKE :query OR p.address ILIKE :query)"
            params['query'] = f"%{query}%"

        sql += " ORDER BY distance LIMIT :limit"
        params['limit'] = limit

        result = await db.execute(text(sql), params)
        rows = result.fetchall()

        # Convert to Place objects
        places = []
        for row in rows:
            place = Place(
                id=row.id,
                name=row.name,
                latitude=row.latitude,
                longitude=row.longitude,
                categories=row.categories,
                rating=row.rating,
                phone=row.phone,
                website=row.website,
                address=row.address,
                city=row.city,
                external_id=row.external_id,
                data_source=row.data_source,
                place_metadata=row.place_metadata,
                last_enriched_at=row.last_enriched_at
            )
            places.append(place)

        return places

    async def _search_places_with_bounding_box(
        self,
        lat: float,
        lon: float,
        radius: int,
        query: Optional[str] = None,
        limit: int = 20,
        db: AsyncSession = None
    ) -> List[Place]:
        """Fallback search using bounding box (original method)"""
        # Calculate bounding box for efficient querying
        # Approximate: 1 degree ≈ 111km
        lat_radius = radius / 111000.0

        # Fix: Use cosine of latitude for longitude radius to prevent divide by zero
        # and handle equator and low latitudes correctly
        import math
        lat_radians = math.radians(abs(lat))
        cos_lat = math.cos(lat_radians)

        # Prevent division by zero and handle edge cases
        if cos_lat < 0.001:  # Very close to equator
            cos_lat = 0.001  # Use minimum value

        lon_radius = radius / (111000.0 * cos_lat)

        min_lat = lat - lat_radius
        max_lat = lat + lat_radius
        min_lon = lon - lon_radius
        max_lon = lon + lon_radius

        # Build query
        stmt = select(Place).where(
            and_(
                Place.latitude >= min_lat,
                Place.latitude <= max_lat,
                Place.longitude >= min_lon,
                Place.longitude <= max_lon
            )
        )

        # Add text search if query provided
        if query:
            stmt = stmt.where(
                or_(
                    Place.name.ilike(f"%{query}%"),
                    Place.categories.ilike(f"%{query}%"),
                    Place.address.ilike(f"%{query}%")
                )
            )

        # Order by distance and limit results
        stmt = stmt.limit(limit * 2)  # Get more to filter by exact distance

        result = await db.execute(stmt)
        places = result.scalars().all()

        # Filter by exact distance and sort
        filtered_places = []
        for place in places:
            distance = haversine_distance(
                lat, lon, place.latitude, place.longitude)
            if distance <= radius:
                filtered_places.append((place, distance))

        # Sort by distance and return top results
        filtered_places.sort(key=lambda x: x[1])
        return [place for place, _ in filtered_places[:limit]]

    def _place_to_dict(self, place: Place) -> Dict[str, Any]:
        """Convert place to dictionary"""
        return {
            'id': place.id,
            'name': place.name,
            'latitude': place.latitude,
            'longitude': place.longitude,
            'categories': place.categories,
            'rating': place.rating,
            'phone': place.phone,
            'website': place.website,
            'address': place.address,
            'city': place.city,
            'external_id': place.external_id,
            'data_source': place.data_source,
            'metadata': place.place_metadata,
            'last_enriched_at': place.last_enriched_at.isoformat() if place.last_enriched_at else None
        }


# Global instance
enhanced_place_data_service = EnhancedPlaceDataService()
