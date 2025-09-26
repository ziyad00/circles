import hashlib
import json
import logging

from ..models import Follow
# from ..routers.activity import create_checkin_activity  # Removed unused activity router
from ..utils import can_view_checkin, haversine_distance
from ..services.place_data_service_v2 import enhanced_place_data_service, EnhancedPlaceDataService
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
from ..models import (
    Place,
    CheckIn,
    SavedPlace,
    User,
    Review,
    Photo,
    CheckInPhoto,
    ExternalSearchSnapshot,
    UserCollection,
)
from ..services.collection_sync import (
    ensure_default_collection,
    ensure_saved_place_entry,
    normalize_collection_name,
    remove_saved_place_membership,
)
from ..database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, text
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/places", tags=["places"])

logger = logging.getLogger(__name__)


def _parse_time_window(time_window: str) -> timedelta:
    """Parse time window string to timedelta object."""
    try:
        time_window = time_window.lower().strip()
        if time_window.endswith('h'):
            hours = int(time_window[:-1])
            return timedelta(hours=hours)
        elif time_window.endswith('d'):
            days = int(time_window[:-1])
            return timedelta(days=days)
        else:
            # Default to 24h if parsing fails
            return timedelta(hours=24)
    except (ValueError, AttributeError):
        # Default to 24h if parsing fails
        return timedelta(hours=24)


async def _get_dynamic_limit_based_on_checkins(db: AsyncSession, time_window: str) -> int:
    """Calculate dynamic limit based on people who can currently chat (within chat window)."""
    try:
        from ..config import settings

        # Use the chat window from config (default 12 hours)
        chat_window_hours = settings.place_chat_window_hours
        chat_since_time = datetime.now(
            timezone.utc) - timedelta(hours=chat_window_hours)

        # Count unique users who can currently chat (have check-ins within chat window)
        # This represents people who are "present" and can interact
        chat_users_count_query = select(func.count(func.distinct(CheckIn.user_id))).where(
            and_(
                CheckIn.created_at >= chat_since_time,
                CheckIn.expires_at > datetime.now(
                    timezone.utc)  # Check-in hasn't expired
            )
        )
        result = await db.execute(chat_users_count_query)
        chat_users_count = result.scalar() or 0

        # Calculate dynamic limit: minimum 3, maximum 50, based on people who can chat
        # Scale factor: every 2 people who can chat adds 1 to the limit
        # This makes the limit more responsive to actual social activity
        dynamic_limit = max(3, min(50, 3 + (chat_users_count // 2)))

        logger.info(
            f"Chat window: {chat_window_hours}h, People who can chat: {chat_users_count}, Dynamic limit: {dynamic_limit}")
        return dynamic_limit

    except Exception as e:
        logger.error(f"Error calculating dynamic limit: {e}")
        # Fallback to default limit of 3
        return 3


def _time_window_to_hours(time_window: str) -> int:
    mapping = {
        "1h": 1,
        "6h": 6,
        "24h": 24,
        "7d": 24 * 7,
        "30d": 24 * 30,
    }
    return mapping.get(time_window, 24)


async def _get_recent_checkins_count(
    db: AsyncSession,
    place_id: int,
    hours: int,
) -> int:
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = select(func.count(func.distinct(CheckIn.user_id))).where(
            and_(CheckIn.place_id == place_id, CheckIn.created_at >= since)
        )
        result = await db.execute(stmt)
        return int(result.scalar() or 0)
    except Exception as exc:
        logger.warning(
            "Failed to compute recent check-in count for place %s: %s",
            place_id,
            exc,
        )
        return 0


def _convert_to_signed_urls(photo_urls: list[str]) -> list[str]:
    """Convert raw storage keys to signed URLs when needed."""
    signed_urls: list[str] = []
    for url in photo_urls:
        if url and not url.startswith("http"):
            # For local storage, return the full URL
            if settings.storage_backend == "local":
                signed_urls.append(f"http://localhost:8000{url}")
            else:
                # For S3, generate signed URL
                try:
                    signed_urls.append(StorageService.generate_signed_url(url))
                except Exception as exc:  # pragma: no cover - fallback path
                    logger.warning("Failed to sign photo URL %s: %s", url, exc)
                    signed_urls.append(url)
        elif url:
            signed_urls.append(url)
    return signed_urls


def _convert_single_to_signed_url(photo_url: str | None) -> str | None:
    """Convert a single storage key or S3 URL to a signed URL."""
    if not photo_url:
        return None

    if not photo_url.startswith("http"):
        # For local storage, return the full URL
        if settings.storage_backend == "local":
            return f"http://localhost:8000{photo_url}"
        else:
            # For S3, generate signed URL
            try:
                return StorageService.generate_signed_url(photo_url)
            except Exception as exc:  # pragma: no cover - fallback path
                logger.warning(
                    "Failed to sign single photo URL %s: %s", photo_url, exc)
    return photo_url


def _collect_place_photos(place: Place) -> list[str]:
    """Return a deduplicated list of signed photo URLs for a place."""
    photo_candidates: list[str] = []

    primary = _convert_single_to_signed_url(place.photo_url)
    if primary:
        photo_candidates.append(primary)

    if place.additional_photos:
        try:
            additional = place.additional_photos
            if isinstance(additional, str):
                parsed = json.loads(additional)
            else:
                parsed = additional
            if isinstance(parsed, list):
                photo_candidates.extend(
                    _convert_to_signed_urls([p for p in parsed if isinstance(p, str)])
                )
        except json.JSONDecodeError:
            logging.warning("Failed to parse additional_photos for place %s", place.id)

    seen: set[str] = set()
    unique: list[str] = []
    for url in photo_candidates:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    return unique

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

        return PaginatedPlaces(
            items=items,
            total=total,
            limit=filters.limit,
            offset=filters.offset,
        )

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
    limit: int = Query(None, ge=1, le=100,
                       description="Override dynamic limit (optional)"),
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

    **Dynamic Limit:**
    - If limit is not provided, automatically calculates based on people who can currently chat
    - Counts unique users with active check-ins within the chat window (default 12h)
    - Formula: min(50, max(3, 3 + (people_who_can_chat // 2)))
    - More people present = more places returned (up to 50 max, minimum 3)
    - Override with explicit limit parameter if needed

    **Foursquare Enhancement:**
    - Adds external discoveries when local results are insufficient
    - Saves new places to local database for future trending
    - Maintains photo URLs and rich metadata
    """
    if limit is None:
        limit = await _get_dynamic_limit_based_on_checkins(db, time_window)
        logger.info(
            "Using dynamic limit: %s (based on people who can chat)",
            limit,
        )
    else:
        logger.info("Using provided limit: %s", limit)

    logger.info(
        "Trending places request: lat=%s, lng=%s, limit=%s, offset=%s, time_window=%s",
        lat,
        lng,
        limit,
        offset,
        time_window,
    )

    if lat is None or lng is None:
        logger.warning("lat and lng are required for trending places")
        return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

    places_to_use: list[Place] = []

    try:
        fsq_places = await enhanced_place_data_service.fetch_foursquare_trending(
            lat=lat,
            lon=lng,
            limit=limit,
        )
        logger.info("Got %s places from Foursquare API", len(fsq_places))

        if not fsq_places:
            logger.info("No places returned from Foursquare API")
            return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

        try:
            saved_places = await enhanced_place_data_service.save_foursquare_places_to_db(
                fsq_places,
                db,
            )
            await db.commit()
            logger.info("Saved %s places to database", len(saved_places))
        except Exception as save_error:
            logger.error(
                "Failed to save Foursquare places to database: %s",
                save_error,
            )
            await db.rollback()
        else:
            if saved_places:
                logger.info(
                    "First saved place: ID=%s, Name=%s",
                    saved_places[0].id,
                    saved_places[0].name,
                )
                places_to_use = saved_places
                logger.info(
                    "Set places_to_use to %s saved places", len(places_to_use)
                )
            else:
                logger.warning(
                    "No places were saved to database - falling back to empty results"
                )
    except Exception as fetch_error:
        logger.error(
            "Failed to fetch Foursquare trending places: %s",
            fetch_error,
        )
        return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

    now_ts = datetime.now(timezone.utc)
    hours_window = _time_window_to_hours(time_window)
    fsq_items: list[PlaceResponse] = []

    logger.info("Using %s places from database", len(places_to_use))
    if places_to_use:
        logger.info(
            "First place to use: %s - %s",
            type(places_to_use[0]),
            places_to_use[0].name,
        )
        logger.info("First place ID: %s", places_to_use[0].id)
    else:
        logger.warning("No places to use - returning empty results")

    for place in places_to_use:
        try:
            all_photos: list[str] = []
            if place.photo_url:
                all_photos.append(place.photo_url)

            additional_photos_list: list[str] = []
            if hasattr(place, "additional_photos") and place.additional_photos:
                try:
                    if isinstance(place.additional_photos, str):
                        additional_photos_list = json.loads(place.additional_photos)
                    elif isinstance(place.additional_photos, list):
                        additional_photos_list = list(place.additional_photos)
                except json.JSONDecodeError:
                    logger.warning(
                        "Failed to parse additional_photos JSON for place %s",
                        place.name,
                    )
                else:
                    all_photos.extend(additional_photos_list)

            recent_count = await _get_recent_checkins_count(
                db,
                place.id,
                hours_window,
            )

            fsq_items.append(
                PlaceResponse(
                    id=place.id,
                    name=place.name or "Unknown",
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
                    created_at=place.created_at or now_ts,
                    photo_url=place.photo_url,
                    recent_checkins_count=recent_count,
                    postal_code=place.postal_code,
                    cross_street=place.cross_street,
                    formatted_address=place.formatted_address,
                    distance_meters=place.distance_meters,
                    venue_created_at=place.venue_created_at,
                    primary_category=(
                        place.categories.split(",")[0]
                        if place.categories
                        else None
                    ),
                    category_icons=None,
                    photo_urls=all_photos,
                    additional_photos=additional_photos_list,
                )
            )
        except Exception as map_error:
            logger.warning(
                "Failed to map place %s: %s",
                getattr(place, "name", "Unknown"),
                map_error,
            )

    fsq_items.sort(key=lambda item: item.distance_meters or float("inf"))

    return PaginatedPlaces(
        items=fsq_items,
        total=len(fsq_items),
        limit=limit,
        offset=offset,
    )


@router.get("/nearby", response_model=PaginatedPlaces)
async def nearby_places(
    lat: float,
    lng: float,
    radius_m: int = 1000,
    limit: int = Query(None, ge=1, le=100,
                       description="Override dynamic limit (optional)"),
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

    **Dynamic Limit:**
    - If limit is not provided, automatically calculates based on people who can currently chat
    - Counts unique users with active check-ins within the chat window (default 12h)
    - Formula: min(50, max(3, 3 + (people_who_can_chat // 2)))
    - More people present = more places returned (up to 50 max, minimum 3)
    - Override with explicit limit parameter if needed

    **Use Cases:**
    - Discover nearby places with social context
    - Location-based exploration with user activity
    - Distance-sorted place lists with check-in data
    """
    if limit is None:
        limit = await _get_dynamic_limit_based_on_checkins(db, "24h")
        logger.info(
            "Using dynamic limit: %s (based on people who can chat)",
            limit,
        )
    else:
        logger.info("Using provided limit: %s", limit)

    logger.info(
        "Nearby places request: lat=%s, lng=%s, radius=%s, limit=%s, offset=%s",
        lat,
        lng,
        radius_m,
        limit,
        offset,
    )

    if lat is None or lng is None:
        return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

    service = EnhancedPlaceDataService()
    places_to_use: list[Place] = []

    try:
        fsq_places = await service.fetch_foursquare_nearby(
            lat,
            lng,
            limit=limit,
            radius_m=radius_m,
        )

        if not fsq_places:
            logger.info("No places returned from Foursquare API")
            return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

        try:
            saved_places = await service.save_foursquare_places_to_db(
                fsq_places,
                db,
            )
            await db.commit()
            logger.info(
                "Saved %s new Foursquare places to database",
                len(saved_places),
            )
            places_to_use = saved_places[:limit] if saved_places else []
        except Exception as save_error:
            logger.warning(
                "Failed to save Foursquare places to database: %s",
                save_error,
            )
            await db.rollback()
    except Exception as fetch_error:
        logger.error("Error fetching nearby places: %s", fetch_error)
        return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

    now_ts = datetime.now(timezone.utc)
    hours_window = 24
    fsq_items: list[PlaceResponse] = []

    for place in places_to_use:
        try:
            all_photos: list[str] = []
            if place.photo_url:
                all_photos.append(place.photo_url)

            additional_photos_list: list[str] = []
            if hasattr(place, "additional_photos") and place.additional_photos:
                try:
                    if isinstance(place.additional_photos, str):
                        additional_photos_list = json.loads(
                            place.additional_photos
                        )
                    elif isinstance(place.additional_photos, list):
                        additional_photos_list = list(place.additional_photos)
                except json.JSONDecodeError:
                    logger.warning(
                        "Failed to parse additional_photos JSON for place %s",
                        place.name,
                    )
                else:
                    all_photos.extend(additional_photos_list)

            recent_count = await _get_recent_checkins_count(
                db,
                place.id,
                hours_window,
            )

            fsq_items.append(
                PlaceResponse(
                    id=place.id,
                    name=place.name or "Unknown",
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
                    created_at=place.created_at or now_ts,
                    photo_url=place.photo_url,
                    recent_checkins_count=recent_count,
                    postal_code=place.postal_code,
                    cross_street=place.cross_street,
                    formatted_address=place.formatted_address,
                    distance_meters=place.distance_meters,
                    venue_created_at=place.venue_created_at,
                    primary_category=(
                        place.categories.split(",")[0]
                        if place.categories
                        else None
                    ),
                    category_icons=None,
                    photo_urls=all_photos,
                    additional_photos=additional_photos_list,
                )
            )
        except Exception as map_error:
            logger.warning(
                "Failed to map place %s: %s",
                getattr(place, "name", "Unknown"),
                map_error,
            )

    fsq_items.sort(key=lambda item: item.distance_meters or float("inf"))

    return PaginatedPlaces(
        items=fsq_items,
        total=len(fsq_items),
        limit=limit,
        offset=offset,
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

        saved_result = await db.execute(
            select(SavedPlace.id).where(
                and_(
                    SavedPlace.user_id == current_user.id,
                    SavedPlace.place_id == place_id,
                )
            )
        )
        is_saved = saved_result.scalar_one_or_none() is not None

        recent_checkins_query = (
            select(CheckIn)
            .where(CheckIn.place_id == place_id)
            .order_by(desc(CheckIn.created_at))
            .limit(10)
        )
        recent_checkins_result = await db.execute(recent_checkins_query)
        recent_checkins = recent_checkins_result.scalars().all()

        checkin_responses: list[CheckInResponse] = []
        aggregated_photo_urls: list[str] = []
        place_photo_candidates = _collect_place_photos(place)
        now = datetime.now(timezone.utc)
        time_limit = timedelta(hours=6)

        for checkin in recent_checkins:
            checkin_created_at = (
                checkin.created_at.replace(tzinfo=timezone.utc)
                if checkin.created_at.tzinfo is None
                else checkin.created_at
            )
            allowed_to_chat = (now - checkin_created_at) < time_limit

            photo_query = select(CheckInPhoto).where(
                CheckInPhoto.check_in_id == checkin.id
            )
            photo_result = await db.execute(photo_query)
            photos = photo_result.scalars().all()
            raw_photo_urls = [photo.url for photo in photos if photo.url]
            signed_photo_urls = _convert_to_signed_urls(raw_photo_urls)

            if not signed_photo_urls and checkin.photo_url:
                single_signed = _convert_single_to_signed_url(checkin.photo_url)
                if single_signed:
                    signed_photo_urls = [single_signed]

            if not signed_photo_urls and place_photo_candidates:
                signed_photo_urls = place_photo_candidates[:1]

            aggregated_photo_urls.extend(signed_photo_urls)

            checkin_responses.append(
                CheckInResponse(
                    id=checkin.id,
                    user_id=checkin.user_id,
                    place_id=checkin.place_id,
                    note=checkin.note,
                    visibility=checkin.visibility,
                    created_at=checkin.created_at,
                    expires_at=checkin.expires_at,
                    latitude=checkin.latitude,
                    longitude=checkin.longitude,
                    photo_url=(
                        signed_photo_urls[0]
                        if signed_photo_urls
                        else _convert_single_to_signed_url(checkin.photo_url)
                    ),
                    photo_urls=signed_photo_urls,
                    allowed_to_chat=allowed_to_chat,
                )
            )

        place_stats = PlaceStats(
            place_id=place.id,
            average_rating=place.rating,
            reviews_count=0,  # TODO: Calculate actual reviews count
            active_checkins=len(recent_checkins),
        )

        if place_photo_candidates:
            aggregated_photo_urls[0:0] = place_photo_candidates

        seen_urls: set[str] = set()
        unique_photos: list[str] = []
        for url in aggregated_photo_urls:
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_photos.append(url)

        primary_photo = unique_photos[0] if unique_photos else None
        if not primary_photo and place_photo_candidates:
            primary_photo = place_photo_candidates[0]

        return EnhancedPlaceResponse(
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
            photo_url=primary_photo,
            photos=unique_photos,
            created_at=place.created_at,
            stats=place_stats,
            current_checkins=len(recent_checkins),
            total_checkins=len(recent_checkins),  # TODO: Calculate actual total check-ins
            recent_reviews=0,  # TODO: Calculate recent reviews
            photos_count=len(unique_photos),
            is_checked_in=False,  # TODO: Check if current user is checked in
            is_saved=is_saved,
        )

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

        photos_query = (
            select(CheckInPhoto.url)
            .join(CheckIn, CheckInPhoto.check_in_id == CheckIn.id)
            .where(
                CheckIn.place_id == place_id,
                CheckInPhoto.url.isnot(None),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await db.execute(photos_query)
        photos = result.scalars().all()

        signed_photos = _convert_to_signed_urls([p for p in photos if p])

        place_photo_candidates = _collect_place_photos(place)
        ordered = place_photo_candidates + signed_photos

        deduped: list[str] = []
        seen: set[str] = set()
        for url in ordered:
            if url and url not in seen:
                seen.add(url)
                deduped.append(url)

        return deduped

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to get place photos")


@router.get("/debug/photos", include_in_schema=False)
async def debug_checkin_photos():
    """Debug endpoint to check CheckInPhoto data"""
    from ..database import get_db
    from sqlalchemy import text

    try:
        async for db in get_db():
            # Check if there are any check-in photos for user with phone 0535667585
            result = await db.execute(text("""
                SELECT
                    cip.id, cip.url, cip.created_at,
                    ci.id as checkin_id, ci.user_id, ci.place_id,
                    u.name as user_name, u.phone
                FROM check_in_photos cip
                JOIN check_ins ci ON cip.check_in_id = ci.id
                JOIN users u ON ci.user_id = u.id
                WHERE u.phone = '0535667585'
                ORDER BY cip.created_at DESC
                LIMIT 10
            """))

            photos = result.fetchall()

            # Also check total check-ins for this user
            checkins_result = await db.execute(text("""
                SELECT COUNT(*) as total_checkins
                FROM check_ins ci
                JOIN users u ON ci.user_id = u.id
                WHERE u.phone = '0535667585'
            """))

            total_checkins = checkins_result.fetchone()[0]

            return {
                "user_phone": "0535667585",
                "total_checkins": total_checkins,
                "total_photos": len(photos),
                "photos": [
                    {
                        "photo_id": photo.id,
                        "url": photo.url,
                        "created_at": str(photo.created_at),
                        "checkin_id": photo.checkin_id,
                        "user_id": photo.user_id,
                        "user_name": photo.user_name,
                        "place_id": photo.place_id
                    }
                    for photo in photos
                ]
            }
    except Exception as e:
        return {"error": str(e)}


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
        from ..config import settings

        # Get recent check-ins for this place (within chat window from config)
        chat_window_hours = settings.place_chat_window_hours
        time_limit = datetime.now(timezone.utc) - \
            timedelta(hours=chat_window_hours)

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
                    check_in_id=checkin.id,
                    user_id=user.id,
                    user_name=user.name or user.username,
                    username=user.username,
                    user_avatar_url=user.avatar_url,
                    created_at=checkin.created_at,
                    photo_urls=[]  # TODO: Get actual photo URLs from CheckInPhoto
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
        await db.flush()  # Get the ID before committing

        photo_urls: list[str] = []
        if photos:
            storage_service = StorageService()
            for photo in photos:
                try:
                    photo_url = await storage_service.upload_photo(
                        photo,
                        f"checkins/{check_in.id}",
                    )
                    if photo_url:
                        db.add(
                            CheckInPhoto(
                                check_in_id=check_in.id,
                                url=photo_url,
                            )
                        )
                        photo_urls.append(photo_url)
                except Exception as upload_error:
                    logging.warning("Failed to upload photo: %s", upload_error)

        await db.commit()
        await db.refresh(check_in)

        signed_photo_urls = _convert_to_signed_urls(photo_urls)

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
            photo_url=signed_photo_urls[0] if signed_photo_urls else None,
            photo_urls=signed_photo_urls,
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

        desired_name = normalize_collection_name(payload.list_name)
        await ensure_default_collection(db, current_user.id)

        existing_query = select(SavedPlace).where(
            and_(
                SavedPlace.user_id == current_user.id,
                SavedPlace.place_id == payload.place_id,
            )
        )
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()

        if existing and normalize_collection_name(existing.list_name) == desired_name:
            # Idempotent response when already saved in the desired collection
            await db.refresh(existing)
            collection_name = (
                existing.collection.name
                if existing.collection
                else existing.list_name
            )
            return SavedPlaceResponse(
                id=existing.id,
                user_id=existing.user_id,
                place_id=existing.place_id,
                collection_id=existing.collection_id,
                list_name=collection_name,
                created_at=existing.created_at,
                place=place,
            )

        saved_place = await ensure_saved_place_entry(
            db,
            current_user.id,
            payload.place_id,
            desired_name,
        )

        await db.commit()
        await db.refresh(saved_place)

        collection_name = (
            saved_place.collection.name
            if saved_place.collection
            else saved_place.list_name
        )

        return SavedPlaceResponse(
            id=saved_place.id,
            user_id=saved_place.user_id,
            place_id=saved_place.place_id,
            collection_id=saved_place.collection_id,
            list_name=collection_name,
            created_at=saved_place.created_at,
            place=place,
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
    collection_name: Optional[str] = Query(
        None, description="Optional collection name. If omitted, any saved instance will be removed."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Remove a place from user's collections.

    **Authentication Required:** Yes
    """
    try:
        # Find saved place entry for this user/place and collection
        query = select(SavedPlace).join(
            UserCollection, SavedPlace.collection_id == UserCollection.id)

        filters = [
            SavedPlace.user_id == current_user.id,
            SavedPlace.place_id == place_id,
        ]

        if collection_name:
            normalized_name = normalize_collection_name(collection_name)
            filters.append(func.lower(UserCollection.name) == normalized_name.lower())

        query = query.where(and_(*filters))
        result = await db.execute(query)
        saved_place = result.scalar_one_or_none()

        if not saved_place:
            raise HTTPException(
                status_code=404, detail="Saved place not found")

        await remove_saved_place_membership(
            db,
            current_user.id,
            place_id,
            collection_id=saved_place.collection_id,
        )
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
