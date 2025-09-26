"""
Enhanced Place Data Service - OSM Overpass + Foursquare Enrichment
"""

import httpx
import asyncio
import json
import math
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime, timedelta, timezone
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
        self.enrichment_ttl_hot = settings.enrich_ttl_hot_days
        self.enrichment_ttl_cold = settings.enrich_ttl_cold_days
        self.max_enrichment_distance = settings.enrich_max_distance_m
        self.min_name_similarity = settings.enrich_min_name_similarity
        self.trending_radius_m = getattr(
            settings, 'fsq_trending_radius_m', 5000)
        self.use_real_trending = getattr(
            settings, 'fsq_use_real_trending', True)

        # OSM tags to seed
        self.osm_seed_tags = {
            'amenity': ['cafe', 'restaurant', 'fast_food', 'bank', 'atm', 'pharmacy',
                        'hospital', 'school', 'university', 'fuel'],
            'shop': ['supermarket', 'mall'],
            'leisure': ['park', 'fitness_centre']
        }

        # Simple in-memory TTL caches
        # key -> (expires_at, value)
        self._cache_discovery: Dict[str,
                                    Tuple[datetime, List[Dict[str, Any]]]] = {}
        self._cache_venue: Dict[str,
                                Tuple[datetime, Optional[Dict[str, Any]]]] = {}
        self._cache_photos: Dict[str,
                                 Tuple[datetime, List[Dict[str, Any]]]] = {}
        self.cache_ttl_seconds = 300  # 5 minutes

    def _cache_get(self, cache: Dict, key: str):
        now = datetime.now(timezone.utc)
        item = cache.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at <= now:
            cache.pop(key, None)
            return None
        return value

    def _cache_set(self, cache: Dict, key: str, value):
        expires_at = datetime.now(timezone.utc) + \
            timedelta(seconds=self.cache_ttl_seconds)
        cache[key] = (expires_at, value)

    async def fetch_foursquare_trending(
        self,
        lat: float | None,
        lon: float | None,
        limit: int = 20,
        query: str = None,
        categories: str = None,
        min_price: int = None,
        max_price: int = None
    ) -> List[Dict[str, Any]]:
        """Fetch REAL trending venues from Foursquare v2 trending endpoint.

        Uses the actual trending endpoint that shows places with high check-in activity.
        """
        # Validate required parameters
        if lat is None or lon is None:
            logging.warning("lat and lon are required for trending places")
            return []

        logging.info(
            f"DEBUG: API key check - key: {self.foursquare_api_key[:10]}... (length: {len(self.foursquare_api_key) if self.foursquare_api_key else 0})")
        if not self.foursquare_api_key or self.foursquare_api_key == "demo_key_for_testing":
            logging.warning(
                f"No valid Foursquare API key: {self.foursquare_api_key}")
            return []

        cache_key = f"fsq_trending:{round(lat, 4)}:{round(lon, 4)}:{limit}:{self.trending_radius_m}:{query or 'none'}:{categories or 'none'}:{min_price or 'none'}:{max_price or 'none'}"
        cached = self._cache_get(self._cache_discovery, cache_key)
        if cached is not None:
            logging.info(
                f"Returning cached trending results: {len(cached)} places")
            return cached

        logging.info(
            f"No cached results, fetching trending places from Foursquare API...")

        # Try v2 trending endpoint first (real trending), fallback to v3 if needed
        logging.info("Trying Foursquare v2 trending endpoint first")
        try:
            results = await self._fetch_foursquare_trending_v2_real(lat, lon, limit)
            # Cache the results
            self._cache_set(self._cache_discovery, cache_key, results)
            return results
        except Exception as e:
            logging.warning(
                f"v2 trending failed: {e}, falling back to v3 popularity sort")
            results = await self._fetch_foursquare_trending_v3_fallback(lat, lon, limit, query, categories, min_price, max_price)
            # Cache the results
            self._cache_set(self._cache_discovery, cache_key, results)
            return results

    async def _fetch_foursquare_trending_v2_real(
        self,
        lat: float,
        lon: float,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Use the real Foursquare v2 trending endpoint."""
        logging.info("Using Foursquare v2 REAL trending endpoint")

        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
            # v2 trending endpoint - this is the real trending API
            url = "https://api.foursquare.com/v2/venues/trending"
            # For v2 API, use client credentials (not oauth token)
            params = {
                "ll": f"{lat},{lon}",
                "limit": limit,
                "radius": self.trending_radius_m,
                "client_id": "5T23EOYWM05NXX5VUNAZEY4WXJNSQ4Q5J115EVM5BNWUC3LV",
                "client_secret": "YBYIORTLA2DUPRYQDGF0T5URS23AWIMUU22SHAOHU4OAWFIT",
                "v": "20231010"  # API version date
            }

            logging.info(f"Calling v2 trending: {url} with params: {params}")
            resp = await client.get(url, params=params)
            logging.info(f"v2 trending response: {resp.status_code}")

            if resp.status_code != 200:
                logging.error(
                    f"v2 trending failed: {resp.status_code}, response: {resp.text}")
                raise Exception(
                    f"v2 trending failed with status {resp.status_code}")

            data = resp.json()
            venues = data.get("response", {}).get("venues", [])
            logging.info(f"v2 trending returned {len(venues)} venues")

            # Convert v2 format to v3-like format for consistency
            results = []
            for venue in venues:
                try:
                    # Extract v2 venue data and convert to v3-like format
                    location = venue.get("location", {})
                    categories = venue.get("categories", [])

                    converted_venue = {
                        "fsq_place_id": venue.get("id"),  # v2 uses 'id'
                        "name": venue.get("name"),
                        "location": {
                            "address": location.get("address"),
                            "locality": location.get("city"),
                            "region": location.get("state"),
                            "country": location.get("country"),
                            "formatted_address": location.get("formattedAddress", [None])[0] if location.get("formattedAddress") else None
                        },
                        "latitude": location.get("lat"),
                        "longitude": location.get("lng"),
                        "categories": [{"name": cat.get("name")} for cat in categories],
                        "rating": venue.get("rating"),
                        "price": venue.get("price", {}).get("tier") if venue.get("price") else None,
                        "distance": location.get("distance"),
                        "photos": []  # v2 photos would need separate API call
                    }
                    results.append(converted_venue)
                except Exception as e:
                    logging.warning(
                        f"Failed to convert v2 venue {venue.get('name', 'unknown')}: {e}")
                    continue

            return await self._enrich_places_with_photos(results)

    async def _fetch_foursquare_trending_v3_fallback(
        self,
        lat: float,
        lon: float,
        limit: int = 20,
        query: str = None,
        categories: str = None,
        min_price: int = None,
        max_price: int = None
    ) -> List[Dict[str, Any]]:
        """Fallback to v3 API with popularity sort if v2 trending fails."""
        logging.info("Falling back to Foursquare v3 API for trending data")

        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
            url = "https://places-api.foursquare.com/places/search"
            headers = {"Authorization": f"Bearer {self.foursquare_api_key}",
                       "X-Places-Api-Version": "2025-06-17",
                       "Accept": "application/json"}
            params = {
                "ll": f"{lat},{lon}",
                "radius": self.trending_radius_m,
                "limit": min(limit * 2, 50),
                "sort": "POPULARITY",  # Best approximation of trending
                "fields": "fsq_place_id,name,location,categories,rating,hours,website,tel,photos,price,popularity,description"
            }

            # Add search filters
            if query:
                params["query"] = query
            if categories:
                params["categories"] = categories
            if min_price is not None:
                params["min_price"] = min_price
            if max_price is not None:
                params["max_price"] = max_price

            try:
                logging.info(
                    f"Foursquare v3 API request: {url} with params: {params}")
                resp = await client.get(url, headers=headers, params=params)
                logging.info(
                    f"Foursquare v3 API response status: {resp.status_code}")

                if resp.status_code == 400:
                    logging.warning(
                        f"Foursquare v3 API 400 error response: {resp.text}")
                    if 'sort' in resp.text:
                        # Retry without sort parameter
                        params.pop("sort", None)
                        logging.info(
                            f"Retrying without sort parameter: {params}")
                        resp = await client.get(url, headers=headers, params=params)
                        logging.info(
                            f"Retry response status: {resp.status_code}")

                if resp.status_code != 200:
                    logging.warning(
                        f"Foursquare v3 fallback failed: {resp.status_code}, response: {resp.text}")
                    return []

                data = resp.json()
                venues = data.get("results", [])
                logging.info(
                    f"Foursquare v3 API returned {len(venues)} venues")

                # Use existing v3 parsing logic
                results: List[Dict[str, Any]] = []
                for v in venues[:limit]:
                    # v3 API uses 'location' directly for coordinates
                    location = v.get("location", {})
                    vlat = location.get("latitude")
                    vlon = location.get("longitude")

                    # Fallback to geocodes if location doesn't have coordinates
                    if vlat is None or vlon is None:
                        geocodes = v.get("geocodes", {}).get("main", {})
                        vlat = geocodes.get("latitude")
                        vlon = geocodes.get("longitude")

                    # If still no coordinates, use search center as fallback
                    if vlat is None or vlon is None:
                        vlat = lat
                        vlon = lon
                        logging.warning(
                            f"Using search center coordinates for venue {v.get('name')}")

                    # Extract photos
                    photos = []
                    if v.get("photos"):
                        for photo in v.get("photos", []):
                            prefix = photo.get("prefix", "")
                            suffix = photo.get("suffix", "")
                            if prefix and suffix:
                                photo_url = f"{prefix}300x300{suffix}"
                                photos.append(photo_url)

                    # Convert price
                    price_tier = None
                    fsq_price = v.get("price")
                    if fsq_price is not None:
                        price_map = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
                        price_tier = price_map.get(fsq_price)

                    # Get address
                    address = location.get(
                        "formatted_address") or location.get("address")
                    city = location.get("locality") or location.get("city")

                    results.append({
                        "id": None,
                        "name": v.get("name"),
                        "latitude": vlat,
                        "longitude": vlon,
                        "categories": ",".join([c.get("name", "") for c in v.get("categories", [])]) or None,
                        "rating": v.get("rating"),
                        "phone": v.get("tel"),
                        "website": v.get("website"),
                        # v3 API uses 'fsq_place_id'
                        "external_id": v.get("fsq_place_id") or v.get("fsq_id"),
                        "data_source": "foursquare",
                        "photos": photos,
                        "price_tier": price_tier,
                        "popularity": v.get("popularity"),
                        "verified": v.get("verified"),
                        "description": v.get("description"),
                        "address": address,
                        "city": city,
                        "metadata": {
                            "foursquare_id": v.get("fsq_place_id") or v.get("fsq_id"),
                            "review_count": v.get("stats", {}).get("total_ratings"),
                            "photo_count": v.get("stats", {}).get("total_photos"),
                            "discovery_source": "foursquare_v3_trending",
                        },
                    })

                logging.info(
                    f"Foursquare v3 API returning {len(results)} processed results")
                return await self._enrich_places_with_photos(results)

            except Exception as e:
                logging.error(f"Error in Foursquare v3 fallback: {e}")
                return []

    async def _enrich_places_with_photos(
        self,
        venues: List[Dict[str, Any]],
        limit_per_venue: int = 5,
    ) -> List[Dict[str, Any]]:
        """Ensure each venue has photo URLs by calling the v3 photos endpoint when needed."""
        if not venues:
            return venues

        if not self.foursquare_api_key or self.foursquare_api_key == "demo_key_for_testing":
            return venues

        venues_needing_photos: list[tuple[int, Dict[str, Any]]] = [
            (idx, v) for idx, v in enumerate(venues) if not v.get("photos")
        ]
        if not venues_needing_photos:
            return venues

        timeout = httpx.Timeout(settings.http_timeout_seconds)
        semaphore = asyncio.Semaphore(5)

        async with httpx.AsyncClient(timeout=timeout) as client:
            async def fetch(idx: int, venue: Dict[str, Any]):
                fsq_id = venue.get("fsq_place_id") or venue.get("fsq_id")
                if not fsq_id:
                    return idx, []
                async with semaphore:
                    photos = await self._fetch_place_photos(client, fsq_id, limit_per_venue)
                    return idx, photos

            tasks = [fetch(idx, venue)
                     for idx, venue in venues_needing_photos]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logging.warning(f"Failed to enrich place photos: {result}")
                continue

            idx, photos = result
            if photos:
                venues[idx]["photos"] = photos

        return venues

    async def _fetch_place_photos(
        self,
        client: httpx.AsyncClient,
        fsq_id: str,
        limit: int = 5,
    ) -> List[str]:
        """Fetch photo URLs for a single Foursquare place."""
        url = f"https://places-api.foursquare.com/places/{fsq_id}/photos"
        headers = {
            "Authorization": f"Bearer {self.foursquare_api_key}",
            "X-Places-Api-Version": "2025-06-17",
            "Accept": "application/json",
        }
        params = {"limit": limit}

        try:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code != 200:
                logging.debug(
                    f"Photo fetch for {fsq_id} failed with status {resp.status_code}: {resp.text}")
                return []

            data = resp.json()
            # Endpoint may return list or dict with "results"
            items: Any
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("results", [])
            else:
                items = []

            photo_urls: list[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                prefix = item.get("prefix")
                suffix = item.get("suffix")
                if prefix and suffix:
                    photo_urls.append(f"{prefix}300x300{suffix}")

            return photo_urls

        except Exception as exc:
            logging.debug(f"Photo fetch for {fsq_id} raised error: {exc}")
            return []

    async def fetch_foursquare_nearby(
        self,
        lat: float,
        lon: float,
        limit: int = 20,
        radius_m: int = 1000,
        query: str = None,
        categories: str = None,
        min_price: int = None,
        max_price: int = None
    ) -> List[Dict[str, Any]]:
        """Fetch nearby venues from Foursquare v3 API sorted by distance.

        Uses the search endpoint with DISTANCE sorting to find places closest to the user.
        """
        logging.info(
            f"Fetching nearby places from Foursquare API: lat={lat}, lon={lon}, radius={radius_m}m")

        if not self.foursquare_api_key or self.foursquare_api_key == "demo_key_for_testing":
            logging.warning(
                f"No valid Foursquare API key: {self.foursquare_api_key}")
            return []

        cache_key = f"fsq_nearby:{round(lat, 4)}:{round(lon, 4)}:{limit}:{radius_m}:{query or 'none'}:{categories or 'none'}:{min_price or 'none'}:{max_price or 'none'}"
        cached = self._cache_get(self._cache_discovery, cache_key)
        if cached is not None:
            logging.info(
                f"Returning cached nearby results: {len(cached)} places")
            return cached

        logging.info(
            "No cached results, fetching nearby places from Foursquare API...")

        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
            url = "https://places-api.foursquare.com/places/search"
            headers = {
                "Authorization": f"Bearer {self.foursquare_api_key}",
                "X-Places-Api-Version": "2025-06-17",
                "Accept": "application/json"
            }
            params = {
                "ll": f"{lat},{lon}",
                "radius": radius_m,
                "limit": min(limit * 2, 50),
                # Note: DISTANCE sort may not be supported, so we skip it and rely on radius filtering
                "fields": "fsq_place_id,name,location,categories,rating,hours,website,tel,photos,price,distance,description"
            }

            # Add search filters
            if query:
                params["query"] = query
            if categories:
                params["categories"] = categories
            if min_price is not None:
                params["min_price"] = min_price
            if max_price is not None:
                params["max_price"] = max_price

            try:
                logging.info(
                    f"Foursquare v3 nearby API request: {url} with params: {params}")
                resp = await client.get(url, headers=headers, params=params)
                logging.info(
                    f"Foursquare v3 nearby API response status: {resp.status_code}")

                if resp.status_code == 400:
                    logging.warning(
                        f"Foursquare v3 nearby API 400 error response: {resp.text}")
                    if 'sort' in resp.text or 'DISTANCE' in resp.text:
                        # Retry without sort parameter - DISTANCE sort might not be supported
                        params.pop("sort", None)
                        logging.info(
                            f"Retrying nearby without sort parameter: {params}")
                        resp = await client.get(url, headers=headers, params=params)
                        logging.info(
                        f"Nearby retry response status: {resp.status_code}")

                if resp.status_code != 200:
                    logging.warning(
                        f"Foursquare v3 nearby failed: {resp.status_code}, response: {resp.text}")
                    return []

                data = resp.json()
                venues = data.get("results", [])
                logging.info(
                    f"Foursquare v3 nearby API returned {len(venues)} venues")

                # Process venues the same way as trending
                results = []
                for v in venues[:limit]:
                    try:
                        # v3 API uses 'location' directly for coordinates
                        location = v.get("location", {})
                        vlat = location.get("latitude")
                        vlon = location.get("longitude")

                        # Fallback to geocodes if location doesn't have coordinates
                        if vlat is None or vlon is None:
                            geocodes = v.get("geocodes", {}).get("main", {})
                            vlat = geocodes.get("latitude")
                            vlon = geocodes.get("longitude")

                        # If still no coordinates, use search center as fallback
                        if vlat is None or vlon is None:
                            vlat = lat
                            vlon = lon
                            logging.warning(
                                f"Using search center coordinates for venue {v.get('name')}")

                        # Extract photos
                        photos = []
                        if v.get("photos"):
                            for photo in v.get("photos", []):
                                prefix = photo.get("prefix", "")
                                suffix = photo.get("suffix", "")
                                if prefix and suffix:
                                    photo_url = f"{prefix}300x300{suffix}"
                                    photos.append(photo_url)

                        # Convert price
                        price_tier = None
                        fsq_price = v.get("price")
                        if fsq_price is not None:
                            price_map = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
                            price_tier = price_map.get(fsq_price)

                        # Get address
                        address = location.get(
                            "formatted_address") or location.get("address")
                        city = location.get("locality") or location.get("city")

                        results.append({
                            "id": None,
                            "name": v.get("name"),
                            "latitude": vlat,
                            "longitude": vlon,
                            "categories": ",".join([c.get("name", "") for c in v.get("categories", [])]) or None,
                            "rating": v.get("rating"),
                            "phone": v.get("tel"),
                            "website": v.get("website"),
                            # v3 API uses 'fsq_place_id'
                            "external_id": v.get("fsq_place_id") or v.get("fsq_id"),
                            "data_source": "foursquare",
                            "photos": photos,
                            "price_tier": price_tier,
                            "popularity": v.get("popularity"),
                            "verified": v.get("verified"),
                            "description": v.get("description"),
                            "address": address,
                            "city": city,
                            "metadata": {
                                "foursquare_id": v.get("fsq_place_id") or v.get("fsq_id"),
                                "review_count": v.get("stats", {}).get("total_ratings"),
                                "photo_count": v.get("stats", {}).get("total_photos"),
                                "discovery_source": "foursquare_v3_nearby",
                                "distance": v.get("distance"),
                            },
                        })
                    except Exception as e:
                        logging.warning(
                            f"Error processing nearby venue {v.get('fsq_place_id', 'unknown')}: {e}")
                        continue

                # Cache the results
                self._cache_set(self._cache_discovery, cache_key, results)

                logging.info(
                    f"Foursquare v3 nearby API returning {len(results)} processed results")
                return results

            except Exception as e:
                logging.error(f"Error in Foursquare v3 nearby: {e}")
                return []

    async def fetch_foursquare_trending_city(
        self,
        city: str,
        limit: int = 20,
        query: str = None,
        categories: str = None,
        min_price: int = None,
        max_price: int = None,
    ) -> List[Dict[str, Any]]:
        """Fetch trending venues from Foursquare by city name (no radius).

        Uses places/search with the `near` parameter and optional popularity bias.
        """
        if not self.foursquare_api_key or self.foursquare_api_key == "demo_key_for_testing":
            return []

        city_key = city.strip().lower()
        cache_key = f"fsq_trending_city:{city_key}:{limit}:{query or 'none'}:{categories or 'none'}:{min_price or 'none'}:{max_price or 'none'}"
        cached = self._cache_get(self._cache_discovery, cache_key)
        if cached is not None:
            return cached

        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
            url = "https://api.foursquare.com/v3/places/search"
            headers = {"Authorization": self.foursquare_api_key,
                       "Accept": "application/json"}
            params = {
                "near": city,
                "limit": min(limit * 2, 50),
                "sort": "POPULARITY",
                "fields": "fsq_id,name,location,categories,rating,stats,hours,website,tel,photos,price,popularity,verified,description,features",
            }

            # Add search filters to Foursquare API call
            if query:
                params["query"] = query
            if categories:
                params["categories"] = categories
            if min_price is not None:
                params["min_price"] = min_price
            if max_price is not None:
                params["max_price"] = max_price

            try:
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code == 400 and 'sort' in resp.text:
                    params.pop("sort", None)
                    resp = await client.get(url, headers=headers, params=params)
                if resp.status_code != 200:
                    return []

                data = resp.json()
                venues = data.get("results", [])
                results: List[Dict[str, Any]] = []
                for v in venues[:limit]:
                    loc = v.get("geocodes", {}).get("main") or {}
                    vlat = (loc.get("latitude") if loc else None) or v.get(
                        "location", {}).get("latitude")
                    vlon = (loc.get("longitude") if loc else None) or v.get(
                        "location", {}).get("longitude")
                    # Extract photo URLs from Foursquare response
                    photos = []
                    if v.get("photos"):
                        for photo in v.get("photos", []):
                            # Foursquare photos have prefix + suffix format
                            prefix = photo.get("prefix", "")
                            suffix = photo.get("suffix", "")
                            if prefix and suffix:
                                # Create a medium-sized photo URL (300x300)
                                photo_url = f"{prefix}300x300{suffix}"
                                photos.append(photo_url)

                    # Convert Foursquare price (1-4) to price tier symbols
                    price_tier = None
                    fsq_price = v.get("price")
                    if fsq_price is not None:
                        price_map = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
                        price_tier = price_map.get(fsq_price)

                    # Get enhanced address from location
                    location = v.get("location", {})
                    address = location.get(
                        "formatted_address") or location.get("address")
                    city = location.get("locality") or location.get("city")

                    # Check if currently open
                    hours = v.get("hours", {})
                    open_now = hours.get("open_now")

                    results.append({
                        "id": None,
                        "name": v.get("name"),
                        "latitude": vlat,
                        "longitude": vlon,
                        "categories": ",".join([c.get("name", "") for c in v.get("categories", [])]) or None,
                        "rating": v.get("rating"),
                        "phone": v.get("contact", {}).get("phone"),
                        "website": v.get("website"),
                        # v2 API uses 'id' not 'fsq_id'
                        "external_id": v.get("id"),
                        "data_source": "foursquare",
                        "photos": photos,
                        # Enhanced fields
                        "price_tier": price_tier,
                        "popularity": v.get("popularity"),
                        "verified": v.get("verified"),
                        "description": v.get("description"),
                        "address": address,
                        "city": city,
                        "open_now": open_now,
                        "metadata": {
                            "foursquare_id": v.get("id"),  # v2 API uses 'id'
                            "review_count": v.get("stats", {}).get("total_ratings"),
                            "photo_count": v.get("stats", {}).get("total_photos"),
                            # v2 API has check-ins
                            "checkins_count": v.get("stats", {}).get("total_checkins"),
                            "opening_hours": hours.get("display"),
                            "discovery_source": "foursquare_trending_city",
                            "features": v.get("features", []),
                        },
                    })

                self._cache_set(self._cache_discovery, cache_key, results)
                return results
            except Exception:
                return []

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

        start_time = datetime.now(timezone.utc)

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
            query_time_ms = (datetime.now(timezone.utc) -
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
        endpoints = settings.overpass_endpoints or [
            "https://overpass-api.de/api/interpreter"]
        last_error = None
        for idx, ep in enumerate(endpoints):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(settings.http_timeout_seconds),
                    headers={"User-Agent": "Circles-App/1.0"}
                ) as client:
                    response = await client.post(ep, data=query, timeout=30.0)
                    if response.status_code == 200:
                        data = response.json()
                        places = []
                        for element in data.get('elements', []):
                            if element['type'] in ['node', 'way']:
                                place_data = self._parse_overpass_element(
                                    element)
                                if place_data:
                                    places.append(place_data)
                        logger.info(
                            f"Fetched {len(places)} places from Overpass API endpoint {ep}")
                        return places
                    if response.status_code == 429:
                        logger.warning(f"Overpass rate limited on {ep}")
                    elif response.status_code >= 500:
                        logger.error(
                            f"Overpass server error {response.status_code} on {ep}")
                    else:
                        logger.error(
                            f"Overpass HTTP {response.status_code} on {ep}")
            except httpx.TimeoutException:
                logger.error(f"Overpass timeout on {ep}")
                last_error = "timeout"
            except httpx.RequestError as e:
                logger.error(f"Overpass request error on {ep}: {e}")
                last_error = str(e)
            except Exception as e:
                logger.error(f"Overpass unexpected error on {ep}: {e}")
                last_error = str(e)
            # try next endpoint
        logger.error(
            f"All Overpass endpoints failed. Last error: {last_error}")
        return []

    def _build_live_overpass_query(
        self,
        lat: float,
        lon: float,
        radius: int,
        limit: int,
    ) -> str:
        """Construct a focused Overpass query using an around filter."""

        limit_clause = max(min(limit * 3, 300), 30)
        filters: list[str] = []
        for category, tags in self.osm_seed_tags.items():
            for tag in tags:
                filters.append(
                    f'node["{category}"="{tag}"](around:{radius},{lat},{lon});'
                )
                filters.append(
                    f'way["{category}"="{tag}"](around:{radius},{lat},{lon});'
                )

        return (
            "[out:json][timeout:25];\n"
            "(\n"
            f"    {''.join(filters)}\n"
            ");\n"
            f"out center {limit_clause};\n"
        )

    async def search_live_overpass(
        self,
        lat: float,
        lon: float,
        radius: int,
        query: Optional[str] = None,
        types: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fetch live place data from Overpass and return ranked results."""

        overpass_query = self._build_live_overpass_query(
            lat, lon, radius, limit)
        raw_places = await self._fetch_overpass_data(overpass_query)
        if not raw_places:
            return []

        normalized_query = query.lower().strip() if query else None
        normalized_types = {
            t.strip().lower() for t in types or [] if t and t.strip()
        }

        results: list[Dict[str, Any]] = []
        for place in raw_places:
            lat_val = place.get("latitude")
            lon_val = place.get("longitude")
            if lat_val is None or lon_val is None:
                continue

            distance_m = haversine_distance(lat, lon, lat_val, lon_val) * 1000
            if radius > 0 and distance_m > radius:
                continue

            if normalized_query:
                name = place.get("name", "").lower()
                if normalized_query not in name:
                    continue

            if normalized_types:
                category = (place.get("categories") or "").lower()
                category_token = category.split(":", 1)[-1]
                if category and category_token:
                    comparison_pool = {category, category_token}
                else:
                    comparison_pool = {category} if category else set()
                if not comparison_pool.intersection(normalized_types):
                    continue

            enriched_place = dict(place)
            enriched_place.setdefault("data_source", "osm_overpass")
            enriched_place["distance_m"] = round(distance_m, 2)
            results.append(enriched_place)

        results.sort(key=lambda item: item.get("distance_m", math.inf))
        return results[:limit]

    async def reverse_geocode_city(self, lat: float, lon: float) -> Optional[str]:
        """Resolve a city name from coordinates using Nominatim.

        Returns a plain city/locality string or None on failure.
        """
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
                url = "https://nominatim.openstreetmap.org/reverse"
                params = {
                    "lat": lat,
                    "lon": lon,
                    "format": "json",
                    "zoom": 10,
                    "addressdetails": 1,
                }
                headers = {
                    "User-Agent": "circles-backend/1.0 (reverse-geocode)"
                }
                r = await client.get(url, params=params, headers=headers)
                if r.status_code != 200:
                    return None
                data = r.json() or {}
                addr = data.get("address", {})
                # prefer city, then town, then village, then state_district
                return addr.get("city") or addr.get("town") or addr.get("village") or addr.get("state_district")
        except Exception:
            return None

    async def reverse_geocode_details(self, lat: float, lon: float) -> Dict[str, Optional[str]]:
        """Resolve country, city, and neighborhood/suburb from coordinates.

        Returns keys: country, city, neighborhood (values may be None).
        """
        result: Dict[str, Optional[str]] = {
            "country": None, "city": None, "neighborhood": None}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
                url = "https://nominatim.openstreetmap.org/reverse"
                params = {
                    "lat": lat,
                    "lon": lon,
                    "format": "json",
                    "zoom": 14,
                    "addressdetails": 1,
                }
                headers = {
                    "User-Agent": "circles-backend/1.0 (reverse-geocode-details)"}
                r = await client.get(url, params=params, headers=headers)
                if r.status_code != 200:
                    return result
                data = r.json() or {}
                addr = data.get("address", {})
                country = addr.get("country")
                city = addr.get("city") or addr.get("town") or addr.get(
                    "village") or addr.get("state_district")
                neighborhood = (
                    addr.get("neighbourhood")
                    or addr.get("neighborhood")
                    or addr.get("suburb")
                    or addr.get("quarter")
                )
                result.update({"country": country, "city": city,
                              "neighborhood": neighborhood})
                return result
        except Exception:
            return result

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
            place_metadata={
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
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=ttl_days)

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

        # Cache key based on name and coords
        cache_key = f"fsq_find:{place.name.lower()}:{round(place.latitude or 0, 4)}:{round(place.longitude or 0, 4)}"
        cached = self._cache_get(self._cache_venue, cache_key)
        if cached is not None:
            return cached

        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
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
                result = {
                    'fsq_id': best_match['fsq_id'],
                    'name': best_match['name'],
                    'match_score': best_score,
                    'distance': best_match.get('distance', 0)
                }
                self._cache_set(self._cache_venue, cache_key, result)
                return result

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
        cache_key = f"fsq_details:{fsq_id}"
        cached = self._cache_get(self._cache_venue, cache_key)
        if cached is not None:
            return cached

        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
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
                    data = response.json()
                    self._cache_set(self._cache_venue, cache_key, data)
                    return data
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
        cache_key = f"fsq_photos:{fsq_id}"
        cached = self._cache_get(self._cache_photos, cache_key)
        if cached is not None:
            return cached

        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds)) as client:
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
                        self._cache_set(self._cache_photos, cache_key, data)
                        return data
                    elif isinstance(data, dict) and 'results' in data:
                        self._cache_set(self._cache_photos,
                                        cache_key, data.get('results', []))
                        return data.get('results', [])
                    else:
                        logger.warning(
                            f"Unexpected photo response format: {type(data)}")
                        self._cache_set(self._cache_photos, cache_key, [])
                        return []
                elif response.status_code == 401:
                    logger.error(
                        "Foursquare API authentication failed - check API key")
                    self._cache_set(self._cache_photos, cache_key, [])
                    return []
                elif response.status_code == 429:
                    logger.warning("Foursquare API rate limit exceeded")
                    self._cache_set(self._cache_photos, cache_key, [])
                    return []
                elif response.status_code >= 500:
                    logger.error(
                        f"Foursquare API server error: {response.status_code}")
                    self._cache_set(self._cache_photos, cache_key, [])
                    return []
                else:
                    logger.error(
                        f"Foursquare API request failed: {response.status_code}")
                    self._cache_set(self._cache_photos, cache_key, [])
                    return []

            except httpx.TimeoutException:
                logger.error("Foursquare API request timed out")
                self._cache_set(self._cache_photos, cache_key, [])
                return []
            except httpx.RequestError as e:
                logger.error(f"Foursquare API request error: {e}")
                self._cache_set(self._cache_photos, cache_key, [])
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
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.http_timeout_seconds),
                headers={"User-Agent": "Circles-App/1.0"}
            ) as client:
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

        # Extract amenities from FSQ attributes
        amenities = self._extract_fsq_amenities(venue_details)

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
            'amenities': amenities,
            'last_enriched_at': datetime.now(timezone.utc).isoformat(),
            'enrichment_source': 'foursquare'
        })

        place.place_metadata = metadata
        place.last_enriched_at = datetime.now(timezone.utc)

    def _extract_fsq_amenities(self, venue_details: Dict[str, Any]) -> Dict[str, bool]:
        """Extract amenities from Foursquare venue attributes"""
        amenities = {}

        # Get attributes from the venue details
        attrs = (venue_details.get("attributes") or {}).get("groups") or []

        # Mapping of FSQ attribute keys to our amenity names
        amenity_mappings = {
            "wifi": "wifi",
            "outdoor_seating": "outdoor_seating",
            "good_for_kids": "family_friendly",
            "family_friendly": "family_friendly",
            "accepts_credit_cards": "credit_cards",
            "wheelchair_accessible": "wheelchair_accessible",
            "parking": "parking",
            "delivery": "delivery",
            "takeout": "takeout",
            "reservations": "reservations",
            "live_music": "live_music",
            "happy_hour": "happy_hour",
            "brunch": "brunch",
            "breakfast": "breakfast",
            "lunch": "lunch",
            "dinner": "dinner",
            "late_night": "late_night"
        }

        try:
            for grp in attrs:
                for item in grp.get("items", []):
                    key = (item.get("key") or "").lower()
                    val = item.get("value")

                    if key in amenity_mappings:
                        amenity_name = amenity_mappings[key]
                        if isinstance(val, bool):
                            amenities[amenity_name] = val
                        elif isinstance(val, str):
                            amenities[amenity_name] = val.lower() in (
                                "yes", "true", "1", "available")
                        elif val is not None:
                            amenities[amenity_name] = bool(val)
        except Exception as e:
            logger.warning(f"Error extracting FSQ amenities: {e}")

        return amenities

    def _calculate_quality_score(self, place: Place) -> float:
        """Calculate quality score for place"""
        score = 0.0

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
                datetime.now(timezone.utc) - place.last_enriched_at).days
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

    async def save_foursquare_place_to_db(self, place_data: Dict[str, Any], db: AsyncSession) -> Optional[Place]:
        """Save a Foursquare place to the local database.

        Args:
            place_data: Dictionary containing place data from Foursquare
            db: Database session

        Returns:
            Place object (existing or newly created)
        """
        try:
            # Skip if external_id is None to avoid "WHERE external_id IS NULL" query
            external_id = place_data.get('external_id')
            if external_id:
                existing = await db.execute(
                    select(Place).where(Place.external_id == external_id)
                )
                existing_place = existing.scalar_one_or_none()
            else:
                existing_place = None
            if existing_place:
                logger.info(
                    "Place with external_id %s already exists (ID: %s)",
                    place_data.get('external_id'),
                    getattr(existing_place, 'id', 'unknown'),
                )
                return existing_place

            # Fix categories field - convert list to string if needed
            categories = place_data.get('categories')
            if isinstance(categories, list):
                # If it's a list of category names, join them
                if categories and isinstance(categories[0], str):
                    categories = ", ".join(categories)
                # If it's a list of category objects, extract names
                elif categories and isinstance(categories[0], dict):
                    categories = ", ".join(
                        [cat.get('name', '') for cat in categories if cat.get('name')])
                else:
                    categories = None
            elif not isinstance(categories, str):
                categories = None

            # Extract photos - first photo as primary, rest as additional
            photos = place_data.get('photos', [])
            primary_photo = photos[0] if photos else None
            additional_photos = photos[1:] if len(photos) > 1 else []

            place = Place(
                name=place_data.get('name'),
                latitude=place_data.get('latitude'),
                longitude=place_data.get('longitude'),
                categories=categories,  # Now properly converted to string
                rating=place_data.get('rating'),
                phone=place_data.get('phone'),
                website=place_data.get('website'),
                address=place_data.get('address'),
                city=place_data.get('city'),
                external_id=place_data.get('external_id'),
                data_source=place_data.get('data_source', 'foursquare'),
                price_tier=place_data.get('price_tier'),
                place_metadata=json.dumps(place_data.get('metadata', {})),
                last_enriched_at=datetime.now(timezone.utc),
                # Add new Foursquare fields
                cross_street=place_data.get('cross_street'),
                formatted_address=place_data.get('formatted_address'),
                distance_meters=place_data.get('distance_meters'),
                venue_created_at=place_data.get('venue_created_at'),
                photo_url=primary_photo,  # Primary photo
                # Additional photos as JSON string
                additional_photos=json.dumps(
                    additional_photos) if additional_photos else None,
            )

            if place.latitude is not None and place.longitude is not None:
                try:
                    geo = await self.reverse_geocode_details(
                        lat=place.latitude, lon=place.longitude
                    )
                    if not place.city and geo.get("city"):
                        place.city = geo.get("city")
                    if not getattr(place, "country", None) and geo.get("country"):
                        place.country = geo.get("country")
                    if not getattr(place, "neighborhood", None) and geo.get("neighborhood"):
                        place.neighborhood = geo.get("neighborhood")
                except Exception as ex:
                    logger.warning(
                        "Failed to reverse geocode place %s: %s",
                        place.name,
                        ex,
                    )

            db.add(place)
            await db.flush()
            logger.info(
                "Saved Foursquare place: %s (ID: %s)",
                place.name,
                place.id,
            )
            return place

        except Exception as ex:
            logger.error(
                "Failed to save Foursquare place to database: %s", ex
            )
            await db.rollback()

            # If database schema is missing columns, create a temporary Place object
            # without saving to database (for API response purposes)
            if "column" in str(ex).lower() and "does not exist" in str(ex).lower():
                logger.warning(
                    "Database schema missing columns - creating temporary Place object")
                place = Place(
                    name=place_data.get('name'),
                    latitude=place_data.get('latitude'),
                    longitude=place_data.get('longitude'),
                    categories=place_data.get('categories'),
                    rating=place_data.get('rating'),
                    phone=place_data.get('phone'),
                    website=place_data.get('website'),
                    address=place_data.get('address'),
                    city=place_data.get('city'),
                    external_id=place_data.get('external_id'),
                    data_source=place_data.get('data_source', 'foursquare'),
                    price_tier=place_data.get('price_tier'),
                    place_metadata=json.dumps(place_data.get('metadata', {})),
                    last_enriched_at=datetime.now(timezone.utc),
                    # Skip the problematic columns for now
                )
                # Set a temporary ID for API response purposes
                place.id = hash(place_data.get(
                    'external_id', place_data.get('name', ''))) % 1000000
                return place

            return None

    async def save_foursquare_places_to_db(self, places_data: List[Dict[str, Any]], db: AsyncSession) -> List[Place]:
        """Save multiple Foursquare places to the local database.

        Args:
            places_data: List of dictionaries containing place data from Foursquare
            db: Database session

        Returns:
            List of created Place objects
        """
        saved_places: list[Place] = []
        for place_data in places_data:
            place = await self.save_foursquare_place_to_db(place_data, db)
            if place:
                saved_places.append(place)

        if saved_places:
            try:
                await db.commit()
                logger.info(
                    f"Successfully saved {len(saved_places)} Foursquare places to database")
            except Exception as e:
                logger.error(
                    f"Failed to commit Foursquare places to database: {e}")
                await db.rollback()
                return []

        return saved_places


# Global instance
enhanced_place_data_service = EnhancedPlaceDataService()
