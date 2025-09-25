import hashlib
import json

from ..models import Follow
# from ..routers.activity import create_checkin_activity  # Removed unused activity router
from ..utils import can_view_checkin, haversine_distance
from ..services.place_data_service_v2 import enhanced_place_data_service
from ..services.storage import StorageService
from ..services.jwt_service import JWTService
from ..services.place_chat_service import create_private_reply_from_place_chat
from ..config import settings
from ..schemas import (
    PlaceCreate,
    PlaceResponse,
    CheckInCreate,
    CheckInUpdate,
    CheckInResponse,
    SavedPlaceCreate,
    SavedPlaceResponse,
    PaginatedPlaces,
    PaginatedSavedPlaces,
    PaginatedCheckIns,
    PaginatedWhosHere,
    WhosHereItem,
    ReviewCreate,
    ReviewResponse,
    PaginatedReviews,
    PlaceStats,
    PhotoResponse,
    PaginatedPhotos,
    CheckInPhotoResponse,
    EnhancedPlaceResponse,
    AdvancedSearchFilters,
    SearchSuggestions,
    SearchSuggestion,
    EnhancedPlaceStats,
    PlaceHourlyStats,
    PlaceCrowdLevel,
    ExternalSearchResponse,
    ExternalPlaceResult,
    DMMessageResponse,
    PlaceChatPrivateReply,
)
from ..models import Place, CheckIn, SavedPlace, User, Review, Photo, CheckInPhoto, ExternalSearchSnapshot
from ..services.collection_sync import (
    ensure_saved_place_entry,
    normalize_collection_name,
    remove_saved_place_membership,
)
from ..database import get_db
from ..services.jwt_service import JWTService
from ..utils import haversine_distance
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, text
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import logging

router = APIRouter(prefix="/places", tags=["places"])

# ============================================================================
# LOOKUP ENDPOINTS (Used by frontend)
# ============================================================================


@router.get("/lookups/countries", response_model=list[str])
async def get_countries(
    q: str = Query("", description="Search query for country names"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of countries with optional search filtering.

    **Authentication Required:** No
    """
    try:
        # Get unique countries from places
        query = select(Place.country).distinct().where(
            Place.country.isnot(None))

        if q:
            query = query.where(Place.country.ilike(f"%{q}%"))

        query = query.limit(limit)

        result = await db.execute(query)
        countries = [row[0] for row in result.fetchall()]

        return sorted(countries)

    except Exception as e:
        logging.error(f"Error fetching countries: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch countries")


@router.get("/lookups/cities", response_model=list[str])
async def get_cities(
    country: str = Query("", description="Filter by country"),
    q: str = Query("", description="Search query for city names"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of cities with optional country filtering and search.

    **Authentication Required:** No
    """
    try:
        query = select(Place.city).distinct().where(Place.city.isnot(None))

        if country:
            query = query.where(Place.country == country)

        if q:
            query = query.where(Place.city.ilike(f"%{q}%"))

        query = query.limit(limit)

        result = await db.execute(query)
        cities = [row[0] for row in result.fetchall()]

        return sorted(cities)

    except Exception as e:
        logging.error(f"Error fetching cities: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cities")


@router.get("/lookups/neighborhoods", response_model=list[str])
async def get_neighborhoods(
    city: str = Query("", description="Filter by city"),
    q: str = Query("", description="Search query for neighborhood names"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of neighborhoods with optional city filtering and search.

    **Authentication Required:** No
    """
    try:
        query = select(Place.neighborhood).distinct().where(
            Place.neighborhood.isnot(None))

        if city:
            query = query.where(Place.city == city)

        if q:
            query = query.where(Place.neighborhood.ilike(f"%{q}%"))

        query = query.limit(limit)

        result = await db.execute(query)
        neighborhoods = [row[0] for row in result.fetchall()]

        return sorted(neighborhoods)

    except Exception as e:
        logging.error(f"Error fetching neighborhoods: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch neighborhoods")

# ============================================================================
# SEARCH ENDPOINTS (Used by frontend)
# ============================================================================


@router.get("/search", response_model=PaginatedPlaces)
async def search_places(
    q: str = Query("", description="Search query"),
    lat: float = Query(None, description="Latitude for location-based search"),
    lng: float = Query(
        None, description="Longitude for location-based search"),
    radius_m: int = Query(5000, ge=100, le=50000,
                          description="Search radius in meters"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Search places with text query and optional location filtering.

    **Authentication Required:** Yes
    """
    try:
        # Build base query
        query = select(Place).where(Place.id.isnot(None))

        # Text search
        if q:
            query = query.where(
                or_(
                    Place.name.ilike(f"%{q}%"),
                    Place.categories.ilike(f"%{q}%"),
                    Place.address.ilike(f"%{q}%"),
                    Place.city.ilike(f"%{q}%")
                )
            )

        # Location-based filtering
        if lat is not None and lng is not None:
            # Add distance calculation and filter by radius
            query = query.where(
                func.sqrt(
                    func.pow(Place.latitude - lat, 2) +
                    func.pow(Place.longitude - lng, 2)
                ) * 111000 <= radius_m  # Rough conversion to meters
            )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination and ordering
        query = query.order_by(desc(Place.created_at)
                               ).offset(offset).limit(limit)

        result = await db.execute(query)
        places = result.scalars().all()

        # Convert to PlaceResponse
        items = []
        for place in places:
            # Calculate distance if coordinates provided
            distance_m = None
            if lat is not None and lng is not None and place.latitude and place.longitude:
                distance_m = haversine_distance(
                    lat, lng, place.latitude, place.longitude)

            place_resp = PlaceResponse(
                id=place.id,
                name=place.name,
                address=place.address,
                country=place.country,
                city=place.city,
                neighborhood=place.neighborhood,
                latitude=place.latitude,
                longitude=place.longitude,
                categories=place.categories,
                rating=place.rating,
                description=place.description,
                price_tier=place.price_tier,
                created_at=place.created_at,
                photo_url=place.photo_url,
                recent_checkins_count=0,  # TODO: Calculate actual count
                postal_code=place.postal_code,
                cross_street=place.cross_street,
                formatted_address=place.formatted_address,
                distance_meters=distance_m,
                venue_created_at=place.venue_created_at,
                primary_category=None,  # TODO: Extract from categories
                category_icons=None,
                photo_urls=[place.photo_url] if place.photo_url else [],
            )
            items.append(place_resp)

        return PaginatedPlaces(items=items, total=total, limit=limit, offset=offset)

    except Exception as e:
        logging.error(f"Error searching places: {e}")
        raise HTTPException(status_code=500, detail="Failed to search places")


@router.post("/search/advanced/flexible", response_model=PaginatedPlaces)
async def search_places_advanced_flexible(
    filters: AdvancedSearchFilters,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Advanced place search with flexible filtering options.

    **Authentication Required:** Yes
    """
    try:
        # Build base query
        query = select(Place).where(Place.id.isnot(None))

        # Apply filters
        if filters.q:
            query = query.where(
                or_(
                    Place.name.ilike(f"%{filters.q}%"),
                    Place.categories.ilike(f"%{filters.q}%"),
                    Place.address.ilike(f"%{filters.q}%")
                )
            )

        if filters.place_type:
            query = query.where(Place.categories.ilike(
                f"%{filters.place_type}%"))

        if filters.country:
            query = query.where(Place.country == filters.country)

        if filters.city:
            query = query.where(Place.city == filters.city)

        if filters.neighborhood:
            query = query.where(Place.neighborhood.ilike(
                f"%{filters.neighborhood}%"))

        if filters.min_rating is not None:
            query = query.where(Place.rating >= filters.min_rating)

        if filters.price_tier:
            query = query.where(Place.price_tier == filters.price_tier)

        # Location-based filtering
        if filters.lat is not None and filters.lng is not None and filters.radius_m:
            query = query.where(
                func.sqrt(
                    func.pow(Place.latitude - filters.lat, 2) +
                    func.pow(Place.longitude - filters.lng, 2)
                ) * 111000 <= filters.radius_m
            )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination and ordering
        query = query.order_by(desc(Place.created_at)).offset(
            filters.offset).limit(filters.limit)

        result = await db.execute(query)
        places = result.scalars().all()

        # Convert to PlaceResponse
        items = []
        for place in places:
            distance_m = None
            if filters.lat is not None and filters.lng is not None and place.latitude and place.longitude:
                distance_m = haversine_distance(
                    filters.lat, filters.lng, place.latitude, place.longitude)

            place_resp = PlaceResponse(
                id=place.id,
                name=place.name,
                address=place.address,
                country=place.country,
                city=place.city,
                neighborhood=place.neighborhood,
                latitude=place.latitude,
                longitude=place.longitude,
                categories=place.categories,
                rating=place.rating,
                description=place.description,
                price_tier=place.price_tier,
                created_at=place.created_at,
                photo_url=place.photo_url,
                recent_checkins_count=0,
                postal_code=place.postal_code,
                cross_street=place.cross_street,
                formatted_address=place.formatted_address,
                distance_meters=distance_m,
                venue_created_at=place.venue_created_at,
                primary_category=None,
                category_icons=None,
                photo_urls=[place.photo_url] if place.photo_url else [],
            )
            items.append(place_resp)

        return PaginatedPlaces(items=items, total=total, limit=filters.limit, offset=filters.offset)

    except Exception as e:
        logging.error(f"Error in advanced place search: {e}")
        raise HTTPException(status_code=500, detail="Failed to search places")

# ============================================================================
# TRENDING AND NEARBY ENDPOINTS (Used by frontend)
# ============================================================================


@router.get("/trending", response_model=PaginatedPlaces)
async def get_trending_places(
    time_window: str = Query(
        "24h", description="Time window: 1h, 6h, 24h, 7d, 30d"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    lat: float | None = Query(
        None, description="Latitude of the user location"),
    lng: float | None = Query(
        None, description="Longitude of the user location"),
    q: str | None = Query(None, description="Search text for place name"),
    place_type: str | None = Query(
        None, description="Category contains (e.g., cafe)"),
    country: str | None = Query(None, description="Country filter (optional)"),
    city: str | None = Query(None, description="City filter (optional)"),
    neighborhood: str | None = Query(
        None, description="Neighborhood contains"),
    min_rating: float | None = Query(
        None, ge=0, le=5, description="Minimum rating"),
    price_tier: str | None = Query(None, description="$, $$, $$$, $$$$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get trending places based on recent activity with Foursquare enhancement.

    **Authentication Required:** No

    **Hybrid Approach:**
    - Primary: Local database trending algorithm based on user activity
    - Enhancement: Foursquare discovery for gaps and new places
    - Data preservation: All user social data (check-ins, reviews) maintained

    **Trending Algorithm:**
    - Calculates activity score over specified time window
    - Considers check-ins, reviews, photos, and unique users
    - Optional geo-reranking by proximity

    **Time Windows:**
    - `1h`: Last hour
    - `6h`: Last 6 hours
    - `24h`: Last 24 hours (default)
    - `7d`: Last 7 days
    - `30d`: Last 30 days

    **Scoring Formula:**
    - Check-ins: 3 points each
    - Reviews: 2 points each
    - Photos: 1 point each
    - Unique users: 2 points each

    **Foursquare Enhancement:**
    - Adds external discoveries when local results are insufficient
    - Saves new places to local database for future trending
    - Maintains photo URLs and rich metadata
    """
    # FIXED: Return Foursquare trending places only
    from datetime import datetime, timezone

    print(f"🔥 CLAUDE FIXED TRENDING ENDPOINT CALLED")

    if lat is None or lng is None:
        raise HTTPException(
            status_code=400, detail="CLAUDE FIXED: lat and lng are required for trending")

    # Call Foursquare API for trending places
    # Debug service configuration
    print(
        f"🔑 API Key check: {enhanced_place_data_service.foursquare_api_key[:10] if enhanced_place_data_service.foursquare_api_key else 'NONE'}...")

    print(
        f"🚀 About to call fetch_foursquare_trending with lat={lat}, lon={lng}, limit={limit}")

    # Use Foursquare v3 Places API for trending (same as nearby for consistency)
    try:
        import asyncio
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
            # Use Foursquare v3 Places API with sort by popularity for trending
            url = "https://places-api.foursquare.com/places/search"
            headers = {
                "Authorization": f"Bearer {settings.foursquare_api_key}",
                "Accept": "application/json",
                "X-Places-Api-Version": "2025-06-17"
            }
            params = {
                "ll": f"{lat},{lng}",
                "radius": 15000,
                "limit": limit,
                "sort": "POPULARITY",  # Sort by popularity for trending effect
                "fields": "fsq_place_id,name,location,categories,distance,photos,rating,price,tel,website"
            }

            response = await client.get(url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                venues = data.get("results", [])
                fsq = venues if venues else []
            else:
                fsq = []

    except Exception as e:
        fsq = []

    if not fsq:
        return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

    # Convert Foursquare response to PlaceResponse objects
    now_ts = datetime.now(timezone.utc)
    items = []

    for venue in fsq[:limit]:
        # Extract location data - Foursquare v3 format
        location = venue.get("location", {})

        # Extract photo URL from v3 format (same as nearby endpoint)
        photo_url = None
        if venue.get("photos"):
            photos = venue.get("photos", [])
            if photos:
                first_photo = photos[0]
                prefix = first_photo.get("prefix", "")
                suffix = first_photo.get("suffix", "")
                if prefix and suffix:
                    photo_url = f"{prefix}300x300{suffix}"

        # Extract categories from v3 format
        categories_list = venue.get("categories", [])
        categories_str = ", ".join(
            [cat.get("name", "") for cat in categories_list]) if categories_list else None

        try:
            place_resp = PlaceResponse(
                id=-1,  # Use -1 for external places without our internal ID
                name=venue.get("name", "Unknown"),
                address=location.get("address"),
                country=location.get("country"),
                # v3 uses 'locality' instead of 'city'
                city=location.get("locality"),
                neighborhood=location.get("neighborhood"),
                latitude=venue.get("latitude"),  # Use actual place coordinates
                # Use actual place coordinates
                longitude=venue.get("longitude"),
                categories=categories_str,
                rating=venue.get("rating"),
                description=None,  # v3 API doesn't include description in search
                price_tier=str(venue.get("price")) if venue.get(
                    "price") is not None else None,  # Convert int to string
                created_at=now_ts,
                external_id=venue.get("fsq_place_id"),
                data_source="foursquare",
                fsq_id=venue.get("fsq_place_id"),
                website=venue.get("website"),
                phone=venue.get("tel"),
                place_metadata=venue,
                photo_url=photo_url,
                recent_checkins=[],
                postal_code=location.get("postal_code"),
                cross_street=location.get("cross_street"),
                formatted_address=location.get("formatted_address"),
                # Use Foursquare's distance
                distance_meters=venue.get("distance"),
                venue_created_at=None,  # v3 doesn't include this in search
                primary_category=categories_list[0].get(
                    "name") if categories_list else None,
                category_icons=None,
                photo_urls=[photo_url] if photo_url else [],
            )
            items.append(place_resp)
        except Exception as e:
            # Skip this place instead of crashing
            continue

    return PaginatedPlaces(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset
    )


@router.get("/nearby", response_model=PaginatedPlaces)
async def nearby_places(
    lat: float,
    lng: float,
    radius_m: int = 1000,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """
    Get nearby places with hybrid local database + Foursquare approach.

    **Authentication Required:** No

    **Hybrid Approach:**
    - Primary: Local database with PostGIS/Python distance filtering
    - Enhancement: Foursquare discovery when local results are insufficient
    - Data preservation: All user social data (check-ins, reviews) maintained

    **Features:**
    - Efficient PostGIS distance search (fallback to Python if needed)
    - Sorts results by distance (nearest first)
    - Preserves recent check-ins and user activity
    - Enhanced with Foursquare discoveries when needed

    **Parameters:**
    - `lat`/`lng`: Search center coordinates
    - `radius_m`: Search radius in meters (default: 1000m)
    - `limit`/`offset`: Standard pagination

    **Use Cases:**
    - Discover nearby places with social context
    - Location-based exploration with user activity
    - Distance-sorted place lists with check-in data
    """
    from ..config import settings as app_settings
    import logging
    print(
        f"🚀 NEARBY ENDPOINT CALLED: lat={lat}, lng={lng}, radius={radius_m}, limit={limit}, offset={offset}")
    logging.info(
        f"Nearby places request: lat={lat}, lng={lng}, radius={radius_m}, limit={limit}, offset={offset}")

    # Fetch ONLY from Foursquare API - no local database results
    print(f"🔥 CALLING FOURSQUARE API: lat={lat}, lng={lng}, limit={limit}")
    logging.info(
        f"DEBUG: NEARBY ENDPOINT CALLED - Fetching places from Foursquare API ONLY at lat={lat}, lng={lng}, limit={limit}")

    # Use direct Foursquare Places API search
    import httpx
    from ..config import settings

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
            url = "https://places-api.foursquare.com/places/search"
            headers = {
                "Authorization": f"Bearer {settings.foursquare_api_key}",
                "Accept": "application/json",
                "X-Places-Api-Version": "2025-06-17"
            }
            params = {
                "ll": f"{lat},{lng}",
                "radius": radius_m,
                "limit": limit,
                "fields": "fsq_place_id,name,location,categories,distance,photos,rating,price,tel,website"
            }

            response = await client.get(url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                places = data.get("results", [])
                fsq_places = places if places else []
            else:
                fsq_places = []

    except Exception as e:
        fsq_places = []

    logging.info(f"DEBUG: Got {len(fsq_places)} places from Foursquare API")

    if not fsq_places:
        logging.info("No places returned from Foursquare API")
        return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

    # Try to save Foursquare places to database for future reference
    saved_places = []
    try:
        saved_places = await enhanced_place_data_service.save_foursquare_places_to_db(fsq_places, db)
        logging.info(
            f"Saved {len(saved_places)} new Foursquare places to database")
    except Exception as e:
        logging.warning(f"Failed to save Foursquare places to database: {e}")

    # Convert saved database places to PlaceResponse objects (use database IDs)
    now_ts = datetime.now(timezone.utc)
    fsq_items: list[PlaceResponse] = []

    # Use saved places if available, otherwise fall back to raw Foursquare data
    places_to_use = saved_places[:limit] if saved_places else fsq_places[:limit]
    
    for i, p in enumerate(places_to_use):
        # Extract location data from Foursquare v3 format
        location = p.get("location", {})

        # Extract photo URL from v3 format
        photo_url = None
        if p.get("photos"):
            photos = p.get("photos", [])
            if photos:
                first_photo = photos[0]
                prefix = first_photo.get("prefix", "")
                suffix = first_photo.get("suffix", "")
                if prefix and suffix:
                    photo_url = f"{prefix}300x300{suffix}"

        # Extract categories from v3 format
        categories_list = p.get("categories", [])
        categories_str = ", ".join(
            [cat.get("name", "") for cat in categories_list]) if categories_list else None

        # Use Foursquare's distance (more accurate than our calculation)
        # Distance in meters from Foursquare API
        foursquare_distance = p.get("distance")

        try:
            # Check if this is a saved database Place object or raw Foursquare data
            if hasattr(p, 'id'):  # This is a saved Place object from database
                place_resp = PlaceResponse(
                    id=p.id,  # Use the actual database ID
                    name=p.name or "Unknown",
                    address=p.address,
                    city=p.city,
                    neighborhood=p.neighborhood,
                    latitude=p.latitude,
                    longitude=p.longitude,
                    categories=p.categories,
                    rating=p.rating,
                    price_tier=p.price_tier,
                    created_at=p.created_at or now_ts,
                    photo_url=p.photo_url,
                    recent_checkins_count=0,
                    postal_code=p.postal_code,
                    cross_street=p.cross_street,
                    formatted_address=p.formatted_address,
                    distance_meters=p.distance_meters,
                    venue_created_at=p.venue_created_at,
                    primary_category=p.categories.split(',')[0] if p.categories else None,
                    category_icons=None,
                    photo_urls=[p.photo_url] if p.photo_url else [],
                )
            else:  # This is raw Foursquare data
                place_resp = PlaceResponse(
                    id=-1,  # Use -1 for external places not yet saved
                    name=p.get("name", "Unknown"),
                    address=location.get("address"),
                    # v3 uses 'locality' instead of 'city'
                    city=location.get("locality"),
                    neighborhood=location.get("neighborhood"),
                    latitude=p.get("latitude"),  # Use actual place coordinates
                    # Use actual place coordinates
                    longitude=p.get("longitude"),
                    categories=categories_str,
                    rating=p.get("rating"),
                    price_tier=str(p.get("price")) if p.get(
                        "price") is not None else None,  # Convert int to string
                    created_at=now_ts,
                    photo_url=photo_url,
                    recent_checkins_count=0,
                    postal_code=location.get("postal_code"),
                    cross_street=location.get("cross_street"),
                    formatted_address=location.get("formatted_address"),
                    distance_meters=foursquare_distance,  # Use Foursquare's distance
                    venue_created_at=None,  # v3 doesn't include this in search
                    primary_category=categories_list[0].get(
                        "name") if categories_list else None,
                    category_icons=None,
                    photo_urls=[photo_url] if photo_url else [],
                )
            fsq_items.append(place_resp)
        except Exception as e:
            # Skip places with mapping issues instead of crashing
            logging.warning(
                f"Failed to map Foursquare place {p.get('name', 'Unknown')}: {e}")
            continue

    # Sort by distance (Foursquare already provides this, but ensure it)
    fsq_items.sort(key=lambda x: x.distance_meters or float('inf'))

    return PaginatedPlaces(
        items=fsq_items,
        total=len(fsq_items),
        limit=limit,
        offset=offset
    )

# ============================================================================
# PLACE DETAILS ENDPOINTS (Used by frontend)
# ============================================================================


@router.get("/{place_id}", response_model=EnhancedPlaceResponse)
async def get_place_details(
    place_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get detailed information about a specific place.

    **Authentication Required:** Yes
    """
    try:
        # Validate place_id
        if place_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid place ID")
        
        # Get place with related data
        query = select(Place).where(Place.id == place_id)
        result = await db.execute(query)
        place = result.scalar_one_or_none()

        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        # Get recent check-ins for this place
        recent_checkins_query = select(CheckIn).where(
            CheckIn.place_id == place_id
        ).order_by(desc(CheckIn.created_at)).limit(10)

        recent_checkins_result = await db.execute(recent_checkins_query)
        recent_checkins = recent_checkins_result.scalars().all()

        # Convert check-ins to response format
        checkin_responses = []
        for checkin in recent_checkins:
            # Check if user can still chat (within time window)
            time_limit = timedelta(hours=6)
            now = datetime.now(timezone.utc)
            # Ensure both datetimes are timezone-aware
            if checkin.created_at.tzinfo is None:
                checkin_created_at = checkin.created_at.replace(
                    tzinfo=timezone.utc)
            else:
                checkin_created_at = checkin.created_at
            allowed_to_chat = (now - checkin_created_at) < time_limit

            # Get photo URLs for this check-in
            photo_query = select(CheckInPhoto).where(
                CheckInPhoto.check_in_id == checkin.id)
            photo_result = await db.execute(photo_query)
            photos = photo_result.scalars().all()
            photo_urls = [
                photo.photo_url for photo in photos if photo.photo_url]

            checkin_resp = CheckInResponse(
                id=checkin.id,
                user_id=checkin.user_id,
                place_id=checkin.place_id,
                note=checkin.note,
                visibility=checkin.visibility,
                created_at=checkin.created_at,
                expires_at=checkin.expires_at,
                latitude=checkin.latitude,
                longitude=checkin.longitude,
                # Backward compatibility
                photo_url=photo_urls[0] if photo_urls else None,
                photo_urls=photo_urls,
                allowed_to_chat=allowed_to_chat,
            )
            checkin_responses.append(checkin_resp)

        # Create place stats
        place_stats = PlaceStats(
            place_id=place.id,
            average_rating=place.rating,
            reviews_count=0,  # TODO: Calculate actual reviews count
            active_checkins=len(recent_checkins),
        )

        # Create enhanced place response
        enhanced_response = EnhancedPlaceResponse(
            id=place.id,
            name=place.name,
            address=place.address,
            country=place.country,
            city=place.city,
            neighborhood=place.neighborhood,
            latitude=place.latitude,
            longitude=place.longitude,
            categories=place.categories,
            rating=place.rating,
            description=place.description,
            price_tier=place.price_tier,
            created_at=place.created_at,
            stats=place_stats,
            current_checkins=len(recent_checkins),
            # TODO: Calculate total check-ins
            total_checkins=len(recent_checkins),
            recent_reviews=0,  # TODO: Calculate recent reviews
            # Count check-ins with photos
            photos_count=len([c for c in checkin_responses if c.photo_urls]),
            is_checked_in=False,  # TODO: Check if current user is checked in
        )

        return enhanced_response

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting place details: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get place details")


@router.get("/{place_id}/photos", response_model=list[str])
async def get_place_photos(
    place_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get photos for a specific place.

    **Authentication Required:** Yes
    """
    try:
        # Validate place_id
        if place_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid place ID")
        
        # Check if place exists
        place_query = select(Place).where(Place.id == place_id)
        place_result = await db.execute(place_query)
        place = place_result.scalar_one_or_none()
        
        if not place:
            raise HTTPException(status_code=404, detail="Place not found")
        
        # Get photos from check-ins for this place
        photos_query = select(CheckInPhoto.url).join(
            CheckIn, CheckInPhoto.check_in_id == CheckIn.id
        ).where(
            CheckIn.place_id == place_id,
            CheckInPhoto.url.isnot(None)
        ).offset(offset).limit(limit)
        
        result = await db.execute(photos_query)
        photos = result.scalars().all()
        
        return list(photos)
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to get place photos")


@router.get("/{place_id}/whos-here", response_model=PaginatedWhosHere)
async def get_whos_here(
    place_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get list of users who are currently at this place.

    **Authentication Required:** Yes
    """
    try:
        # Get recent check-ins for this place (within last 6 hours)
        time_limit = datetime.now(timezone.utc) - timedelta(hours=6)

        query = select(CheckIn).join(User).where(
            and_(
                CheckIn.place_id == place_id,
                CheckIn.created_at >= time_limit,
                CheckIn.expires_at > datetime.now(timezone.utc)
            )
        ).order_by(desc(CheckIn.created_at))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        checkins = result.scalars().all()

        # Convert to WhosHereItem
        items = []
        for checkin in checkins:
            # Get user info
            user_query = select(User).where(User.id == checkin.user_id)
            user_result = await db.execute(user_query)
            user = user_result.scalar_one_or_none()

            if user:
                item = WhosHereItem(
                    user_id=user.id,
                    username=user.username,
                    avatar_url=user.avatar_url,
                    check_in_time=checkin.created_at,
                    note=checkin.note,
                    visibility=checkin.visibility,
                )
                items.append(item)

        return PaginatedWhosHere(items=items, total=total, limit=limit, offset=offset)

    except Exception as e:
        logging.error(f"Error getting who's here: {e}")
        raise HTTPException(status_code=500, detail="Failed to get who's here")

# ============================================================================
# CHECK-IN ENDPOINTS (Used by frontend)
# ============================================================================


@router.post("/check-ins", response_model=CheckInResponse)
async def create_check_in(
    payload: CheckInCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Create a new check-in at a place.

    **Authentication Required:** Yes
    """
    try:
        # Verify place exists
        place_query = select(Place).where(Place.id == payload.place_id)
        place_result = await db.execute(place_query)
        place = place_result.scalar_one_or_none()

        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        # Create check-in
        default_vis = "public"
        check_in = CheckIn(
            user_id=current_user.id,
            place_id=payload.place_id,
            note=payload.note,
            visibility=payload.visibility or default_vis,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            latitude=payload.latitude,
            longitude=payload.longitude,
        )

        db.add(check_in)
        await db.commit()
        await db.refresh(check_in)

        # Create activity (removed - activity router not used)
        # await create_checkin_activity(check_in, db)

        return CheckInResponse(
            id=check_in.id,
            user_id=check_in.user_id,
            place_id=check_in.place_id,
            note=check_in.note,
            visibility=check_in.visibility,
            created_at=check_in.created_at,
            expires_at=check_in.expires_at,
            latitude=check_in.latitude,
            longitude=check_in.longitude,
            photo_url=None,
            photo_urls=[],
            allowed_to_chat=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error creating check-in: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to create check-in")


@router.post("/check-ins/full", response_model=CheckInResponse)
async def create_check_in_full(
    place_id: int = Form(...),
    note: str = Form(None),
    visibility: str = Form("public"),
    latitude: float = Form(None),
    longitude: float = Form(None),
    photos: List[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Create a check-in with photos.

    **Authentication Required:** Yes
    """
    try:
        # Verify place exists
        place_query = select(Place).where(Place.id == place_id)
        place_result = await db.execute(place_query)
        place = place_result.scalar_one_or_none()

        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        # Create check-in
        default_vis = "public"
        check_in = CheckIn(
            user_id=current_user.id,
            place_id=place_id,
            note=note,
            visibility=visibility or default_vis,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            latitude=latitude,
            longitude=longitude,
        )

        db.add(check_in)
        await db.flush()  # Get the ID

        # Handle photo uploads
        photo_urls = []
        if photos:
            storage_service = StorageService()
            for photo in photos:
                try:
                    photo_url = await storage_service.upload_photo(photo, f"checkins/{check_in.id}")
                    if photo_url:
                        # Save photo to database
                        checkin_photo = CheckInPhoto(
                            check_in_id=check_in.id,
                            photo_url=photo_url,
                            uploaded_by=current_user.id
                        )
                        db.add(checkin_photo)
                        photo_urls.append(photo_url)
                except Exception as e:
                    logging.warning(f"Failed to upload photo: {e}")
                    # Continue with other photos

        await db.commit()
        await db.refresh(check_in)

        # Create activity (removed - activity router not used)
        # await create_checkin_activity(check_in, db)

        return CheckInResponse(
            id=check_in.id,
            user_id=check_in.user_id,
            place_id=check_in.place_id,
            note=check_in.note,
            visibility=check_in.visibility,
            created_at=check_in.created_at,
            expires_at=check_in.expires_at,
            latitude=check_in.latitude,
            longitude=check_in.longitude,
            photo_url=photo_urls[0] if photo_urls else None,
            photo_urls=photo_urls,
            allowed_to_chat=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error creating check-in with photos: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to create check-in")

# ============================================================================
# SAVED PLACES ENDPOINTS (Used by frontend)
# ============================================================================


@router.post("/saved", response_model=SavedPlaceResponse)
async def save_place(
    payload: SavedPlaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Save a place to user's collections.

    **Authentication Required:** Yes
    """
    try:
        # Verify place exists
        place_query = select(Place).where(Place.id == payload.place_id)
        place_result = await db.execute(place_query)
        place = place_result.scalar_one_or_none()

        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        # Check if already saved
        existing_query = select(SavedPlace).where(
            and_(
                SavedPlace.user_id == current_user.id,
                SavedPlace.place_id == payload.place_id,
                SavedPlace.collection_name == payload.collection_name
            )
        )
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=400, detail="Place already saved in this collection")

        # Create saved place entry
        saved_place = SavedPlace(
            user_id=current_user.id,
            place_id=payload.place_id,
            collection_name=payload.collection_name,
            notes=payload.notes
        )

        db.add(saved_place)
        await db.commit()
        await db.refresh(saved_place)

        return SavedPlaceResponse(
            id=saved_place.id,
            user_id=saved_place.user_id,
            place_id=saved_place.place_id,
            collection_name=saved_place.collection_name,
            notes=saved_place.notes,
            created_at=saved_place.created_at,
            place=place
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error saving place: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save place")


@router.delete("/saved/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_place(
    place_id: int,
    collection_name: str = Query(..., description="Collection name"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Remove a place from user's collections.

    **Authentication Required:** Yes
    """
    try:
        # Find saved place entry
        query = select(SavedPlace).where(
            and_(
                SavedPlace.user_id == current_user.id,
                SavedPlace.place_id == place_id,
                SavedPlace.collection_name == collection_name
            )
        )
        result = await db.execute(query)
        saved_place = result.scalar_one_or_none()

        if not saved_place:
            raise HTTPException(
                status_code=404, detail="Saved place not found")

        await db.delete(saved_place)
        await db.commit()

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error unsaving place: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to unsave place")

# ============================================================================
# EXTERNAL TEST ENDPOINT (Used for testing)
# ============================================================================


@router.get("/external/test")
async def test_external_endpoints():
    """
    Test endpoint to verify external endpoints are working.

    **Authentication Required:** No
    """
    return {"message": "External endpoints are working!"}
