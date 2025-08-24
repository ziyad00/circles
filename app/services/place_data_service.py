"""
Place Data Service - Handles place data from multiple sources
"""

import httpx
import asyncio
from typing import List, Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Place
from ..config import settings
import logging

logger = logging.getLogger(__name__)


class PlaceDataService:
    """Service for fetching and managing place data from multiple sources"""

    def __init__(self):
        self.google_api_key = getattr(settings, 'google_places_api_key', None)
        self.foursquare_api_key = getattr(settings, 'foursquare_api_key', None)
        self.openstreetmap_enabled = getattr(
            settings, 'use_openstreetmap', True)

    async def search_nearby_places(
        self,
        lat: float,
        lon: float,
        radius: int = 5000,
        query: Optional[str] = None,
        types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for places near a location using multiple sources

        Args:
            lat: Latitude
            lon: Longitude  
            radius: Search radius in meters
            query: Optional search query
            types: Optional place types to filter by

        Returns:
            List of place data dictionaries
        """
        places = []

        # Try Google Places first (if API key available)
        if self.google_api_key:
            try:
                google_places = await self._search_google_places(lat, lon, radius, query, types)
                places.extend(google_places)
            except Exception as e:
                logger.warning(f"Google Places search failed: {e}")

        # Fallback to OpenStreetMap
        if self.openstreetmap_enabled:
            try:
                osm_places = await self._search_openstreetmap(lat, lon, radius, query)
                places.extend(osm_places)
            except Exception as e:
                logger.warning(f"OpenStreetMap search failed: {e}")

        # Remove duplicates and return
        return self._deduplicate_places(places)

    async def get_place_details(self, place_id: str, source: str = "google") -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific place

        Args:
            place_id: Place identifier
            source: Data source ("google", "foursquare", "osm")

        Returns:
            Detailed place information
        """
        if source == "google" and self.google_api_key:
            return await self._get_google_place_details(place_id)
        elif source == "foursquare" and self.foursquare_api_key:
            return await self._get_foursquare_place_details(place_id)
        elif source == "osm":
            return await self._get_osm_place_details(place_id)

        return None

    async def enrich_place_data(self, place: Place) -> Place:
        """
        Enrich existing place data with additional information

        Args:
            place: Place model instance

        Returns:
            Enriched place data
        """
        # Get additional details from external APIs
        if place.external_id and place.data_source:
            details = await self.get_place_details(place.external_id, place.data_source)
            if details:
                # Update place with enriched data
                place.rating = details.get('rating', place.rating)
                place.categories = details.get('types', place.categories)
                place.website = details.get('website', place.website)
                place.phone = details.get(
                    'formatted_phone_number', place.phone)

                # Store additional data in JSON field
                place.metadata = {
                    'opening_hours': details.get('opening_hours'),
                    'price_level': details.get('price_level'),
                    'user_ratings_total': details.get('user_ratings_total'),
                    # Limit to 5 photos
                    'photos': details.get('photos', [])[:5],
                    'last_updated': details.get('last_updated')
                }

        return place

    async def _search_google_places(
        self,
        lat: float,
        lon: float,
        radius: int,
        query: Optional[str] = None,
        types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search places using Google Places API"""
        async with httpx.AsyncClient() as client:
            url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            params = {
                'location': f"{lat},{lon}",
                'radius': radius,
                'key': self.google_api_key,
                'type': types[0] if types else None
            }

            if query:
                params['keyword'] = query

            response = await client.get(url, params=params)
            data = response.json()

            if data['status'] == 'OK':
                return [
                    {
                        'name': place['name'],
                        'address': place.get('vicinity'),
                        'latitude': place['geometry']['location']['lat'],
                        'longitude': place['geometry']['location']['lng'],
                        'rating': place.get('rating'),
                        'types': place.get('types', []),
                        'place_id': place['place_id'],
                        'data_source': 'google',
                        'external_id': place['place_id']
                    }
                    for place in data['results']
                ]

            return []

    async def _search_openstreetmap(
        self,
        lat: float,
        lon: float,
        radius: int,
        query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search places using OpenStreetMap Nominatim"""
        async with httpx.AsyncClient() as client:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'format': 'json',
                'limit': 20,
                'lat': lat,
                'lon': lon,
                'radius': radius // 1000,  # Convert to km
                'addressdetails': 1
            }

            if query:
                params['q'] = query

            response = await client.get(url, params=params)
            data = response.json()

            return [
                {
                    'name': place['display_name'].split(',')[0],
                    'address': place['display_name'],
                    'latitude': float(place['lat']),
                    'longitude': float(place['lon']),
                    'place_id': place['place_id'],
                    'data_source': 'osm',
                    'external_id': place['place_id'],
                    'types': [place.get('type', 'unknown')]
                }
                for place in data
                if place.get('type') in ['restaurant', 'cafe', 'bar', 'shop', 'amenity']
            ]

    async def _get_google_place_details(self, place_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed place information from Google Places"""
        async with httpx.AsyncClient() as client:
            url = "https://maps.googleapis.com/maps/api/place/details/json"
            params = {
                'place_id': place_id,
                'fields': 'name,formatted_address,geometry,types,rating,user_ratings_total,photos,opening_hours,price_level,website,formatted_phone_number',
                'key': self.google_api_key
            }

            response = await client.get(url, params=params)
            data = response.json()

            if data['status'] == 'OK':
                place = data['result']
                return {
                    'rating': place.get('rating'),
                    'user_ratings_total': place.get('user_ratings_total'),
                    'types': place.get('types', []),
                    'website': place.get('website'),
                    'formatted_phone_number': place.get('formatted_phone_number'),
                    'opening_hours': place.get('opening_hours', {}).get('weekday_text', []),
                    'price_level': place.get('price_level'),
                    'photos': [
                        {
                            'photo_reference': photo['photo_reference'],
                            'width': photo['width'],
                            'height': photo['height']
                        }
                        for photo in place.get('photos', [])[:5]
                    ],
                    'last_updated': 'google'
                }

            return None

    async def _get_foursquare_place_details(self, venue_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed place information from Foursquare"""
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            url = f"https://api.foursquare.com/v3/places/{venue_id}"
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
                    data = response.json()
                    return {
                        'rating': data.get('rating'),
                        'types': [cat['name'] for cat in data.get('categories', [])],
                        'website': data.get('website'),
                        'formatted_phone_number': data.get('tel'),
                        'photos': data.get('photos', []),
                        'last_updated': 'foursquare'
                    }
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

    async def _get_osm_place_details(self, place_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed place information from OpenStreetMap"""
        async with httpx.AsyncClient() as client:
            url = f"https://nominatim.openstreetmap.org/lookup"
            params = {
                'osm_ids': place_id,
                'format': 'json',
                'addressdetails': 1
            }

            response = await client.get(url, params=params)
            data = response.json()

            if data:
                place = data[0]
                return {
                    'types': [place.get('type', 'unknown')],
                    'last_updated': 'osm'
                }

            return None

    def _deduplicate_places(self, places: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate places based on name and location"""
        seen = set()
        unique_places = []

        for place in places:
            # Create a key based on name and approximate location
            key = f"{place['name'].lower()}_{round(place['latitude'], 4)}_{round(place['longitude'], 4)}"

            if key not in seen:
                seen.add(key)
                unique_places.append(place)

        return unique_places

    async def sync_place_to_database(
        self,
        db: AsyncSession,
        place_data: Dict[str, Any]
    ) -> Place:
        """
        Sync place data to database

        Args:
            db: Database session
            place_data: Place data dictionary

        Returns:
            Place model instance
        """
        # Check if place already exists
        existing_place = await db.execute(
            select(Place).where(
                Place.latitude == place_data['latitude'],
                Place.longitude == place_data['longitude'],
                Place.name == place_data['name']
            )
        )
        existing_place = existing_place.scalar_one_or_none()

        if existing_place:
            # Update existing place with new data
            existing_place.rating = place_data.get(
                'rating', existing_place.rating)
            existing_place.categories = place_data.get(
                'types', existing_place.categories)
            existing_place.external_id = place_data.get(
                'external_id', existing_place.external_id)
            existing_place.data_source = place_data.get(
                'data_source', existing_place.data_source)
            return existing_place
        else:
            # Create new place
            new_place = Place(
                name=place_data['name'],
                address=place_data.get('address'),
                latitude=place_data['latitude'],
                longitude=place_data['longitude'],
                rating=place_data.get('rating'),
                categories=place_data.get('types', []),
                external_id=place_data.get('external_id'),
                data_source=place_data.get('data_source')
            )
            db.add(new_place)
            await db.commit()
            await db.refresh(new_place)
            return new_place


# Global instance
place_data_service = PlaceDataService()
