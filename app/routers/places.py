import hashlib
import json
import logging

from ..models import Follow
# from ..routers.activity import create_checkin_activity  # Removed unused activity router
from ..utils import can_view_checkin, haversine_distance
from ..utils import category_filter, foursquare_filter_mapper
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
    PlaceChatRoom,
    PlaceChatMessageCreate,
    PlaceChatMessageResponse,
    PaginatedPlaceChatMessages,
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
    PlaceChatMessage,
)
from ..services.collection_sync import (
    ensure_default_collection,
    ensure_saved_place_entry,
    normalize_collection_name,
    remove_saved_place_membership,
)
from ..database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, text
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from .dms_ws import manager

router = APIRouter(prefix="/places", tags=["places"])

logger = logging.getLogger(__name__)


def _get_all_place_photos(place) -> list[str]:
    """Helper function to get all photos for a place, combining photo_url and additional_photos."""
    all_photos = []

    # Add primary photo
    if place.photo_url:
        all_photos.append(place.photo_url)

    # Add additional photos
    if hasattr(place, "additional_photos") and place.additional_photos:
        try:
            if isinstance(place.additional_photos, str):
                additional_list = json.loads(place.additional_photos)
            elif isinstance(place.additional_photos, list):
                additional_list = list(place.additional_photos)
            else:
                additional_list = []

            all_photos.extend(additional_list)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"Failed to parse additional_photos for place {getattr(place, 'name', 'unknown')}")

    return all_photos


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
            return timedelta(hours=settings.checkin_expiry_hours)
    except (ValueError, AttributeError):
        # Default to configured expiry if parsing fails
        return timedelta(hours=settings.checkin_expiry_hours)


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
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=hours)
        stmt = select(func.count(func.distinct(CheckIn.user_id))).where(
            and_(
                CheckIn.place_id == place_id,
                CheckIn.created_at >= since,
                CheckIn.expires_at > now  # Only count non-expired check-ins
            )
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
                signed_urls.append(f"{settings.local_base_url}{url}")
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
            return f"{settings.local_base_url}{photo_url}"
        else:
            # For S3, generate signed URL
            try:
                return StorageService.generate_signed_url(photo_url)
            except Exception as exc:  # pragma: no cover - fallback path
                logger.warning(
                    "Failed to sign single photo URL %s: %s", photo_url, exc)
            return photo_url
    elif 's3.amazonaws.com' in photo_url or 'circles-media' in photo_url:
        # Handle existing S3 URLs that need re-signing
        try:
            if '/circles-media' in photo_url:
                s3_key = photo_url.split('/circles-media')[1].lstrip('/')
            elif '.s3.amazonaws.com/' in photo_url:
                s3_key = photo_url.split('.s3.amazonaws.com/')[1]
            else:
                return photo_url
            return StorageService.generate_signed_url(s3_key)
        except Exception as exc:
            logger.warning(
                "Failed to re-sign S3 URL %s: %s", photo_url, exc)
            return photo_url
    else:
        # Already a full URL (e.g., from external sources or local storage)
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
                    _convert_to_signed_urls(
                        [p for p in parsed if isinstance(p, str)])
                )
        except json.JSONDecodeError:
            logging.warning(
                "Failed to parse additional_photos for place %s", place.id)

    seen: set[str] = set()
    unique: list[str] = []
    for url in photo_candidates:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


async def _ensure_user_can_chat(
    db: AsyncSession,
    place_id: int,
    user_id: int,
) -> CheckIn:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=int(settings.place_chat_window_hours))

    query = (
        select(CheckIn)
        .where(
            CheckIn.user_id == user_id,
            CheckIn.place_id == place_id,
            CheckIn.created_at >= window_start,
            CheckIn.expires_at > now,
        )
        .order_by(desc(CheckIn.created_at))
    )

    result = await db.execute(query)
    checkin = result.scalar_one_or_none()
    if not checkin:
        raise HTTPException(
            status_code=403,
            detail="You need a recent check-in at this place to use the chat",
        )
    return checkin


async def _build_place_chat_room(
    db: AsyncSession,
    place: Place,
    current_user_id: int,
) -> PlaceChatRoom:
    now = datetime.now(timezone.utc)
    window_hours = int(settings.place_chat_window_hours)
    window_delta = timedelta(hours=window_hours)
    window_start = now - window_delta

    active_users_query = select(func.count(func.distinct(CheckIn.user_id))).where(
        CheckIn.place_id == place.id,
        CheckIn.created_at >= window_start,
        CheckIn.expires_at > now,
    )
    active_users_count = int((await db.execute(active_users_query)).scalar() or 0)

    latest_checkin_query = select(func.max(CheckIn.created_at)).where(
        CheckIn.place_id == place.id,
        CheckIn.created_at >= window_start,
    )
    latest_checkin = (await db.execute(latest_checkin_query)).scalar()
    expires_at = (latest_checkin + window_delta) if latest_checkin else now

    membership_query = select(CheckIn.id).where(
        CheckIn.user_id == current_user_id,
        CheckIn.place_id == place.id,
        CheckIn.created_at >= window_start,
        CheckIn.expires_at > now,
    )
    has_joined = bool((await db.execute(membership_query)).scalar_one_or_none())

    last_message_query = (
        select(PlaceChatMessage)
        .where(PlaceChatMessage.place_id == place.id)
        .order_by(desc(PlaceChatMessage.created_at))
        .limit(1)
    )
    last_message_row = (await db.execute(last_message_query)).scalar_one_or_none()

    last_message_text = last_message_row.text if last_message_row else None
    last_message_at = last_message_row.created_at if last_message_row else None

    created_at = place.created_at or now
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    return PlaceChatRoom(
        id=place.id,
        place_id=place.id,
        place_name=place.name,
        created_at=created_at,
        expires_at=expires_at,
        active_users_count=active_users_count,
        is_active=active_users_count > 0 and expires_at > now,
        has_joined=has_joined,
        last_message=last_message_text,
        last_message_at=last_message_at,
    )


def _serialize_place_chat_message_response(
    message: PlaceChatMessage,
    user: User,
) -> PlaceChatMessageResponse:
    author_name = user.name or user.username or f"User {user.id}"
    avatar = _convert_single_to_signed_url(user.avatar_url)
    created_at = message.created_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return PlaceChatMessageResponse(
        id=str(message.id),
        room_id=message.place_id,
        place_id=message.place_id,
        user_id=user.id,
        author_id=str(user.id),
        author_name=author_name,
        author_avatar_url=avatar,
        text=message.text,
        created_at=created_at,
        status="sent",
    )


async def _get_place_or_404(db: AsyncSession, place_id: int) -> Place:
    res = await db.execute(select(Place).where(Place.id == place_id))
    place = res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


async def _send_place_chat_payload_to_user(
    place_id: int,
    user_id: int,
    payload: dict,
) -> None:
    thread_id = -int(place_id)
    connection = manager.active.get(thread_id, {}).get(user_id)
    if not connection:
        return
    websocket, _ = connection
    try:
        await websocket.send_json(payload)
    except Exception:
        manager.disconnect(thread_id, user_id, websocket)


def _parse_iso_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - validation path
        raise HTTPException(
            status_code=400,
            detail="Invalid datetime format. Use ISO 8601.",
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed

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
                photo_url=_convert_single_to_signed_url(place.photo_url),
                recent_checkins_count=0,  # TODO: Calculate actual count
                cross_street=place.cross_street,
                formatted_address=place.formatted_address,
                distance_meters=distance_m,
                venue_created_at=place.venue_created_at,
                primary_category=None,  # TODO: Extract from categories
                category_icons=None,
                photo_urls=_get_all_place_photos(place),
            )
            items.append(place_resp)

        return PaginatedPlaces(items=items, total=total, limit=limit, offset=offset)

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Error searching places: {e}\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


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
        if filters.query:
            query = query.where(
                or_(
                    Place.name.ilike(f"%{filters.query}%"),
                    Place.categories.ilike(f"%{filters.query}%"),
                    Place.address.ilike(f"%{filters.query}%")
                )
            )

        if filters.categories:
            for category in filters.categories:
                query = query.where(Place.categories.ilike(f"%{category}%"))

        if filters.country:
            query = query.where(Place.country.ilike(f"%{filters.country}%"))

        if filters.city:
            query = query.where(Place.city == filters.city)

        if filters.neighborhood:
            query = query.where(Place.neighborhood.ilike(
                f"%{filters.neighborhood}%"))

        if filters.rating_min is not None:
            query = query.where(Place.rating >= filters.rating_min)

        if filters.rating_max is not None:
            query = query.where(Place.rating <= filters.rating_max)

        # Activity filters
        if filters.has_recent_checkins is True:
            # Check for places with recent check-ins (last 24 hours)
            from datetime import datetime, timedelta
            recent_time = datetime.utcnow() - timedelta(hours=24)
            query = query.join(CheckIn).where(
                CheckIn.created_at >= recent_time)

        if filters.has_reviews is True:
            # Check for places with reviews (assuming reviews table exists)
            # For now, we'll check if rating is not null as a proxy
            query = query.where(Place.rating.isnot(None))

        if filters.has_photos is True:
            # Check for places with photos (assuming photos table exists)
            # For now, we'll check if photo_url is not null as a proxy
            query = query.where(Place.photo_url.isnot(None))

        # Location-based filtering
        if filters.latitude is not None and filters.longitude is not None and filters.radius_km:
            # Convert km to approximate meters (1 degree ≈ 111km)
            radius_m = filters.radius_km * 1000
            query = query.where(
                func.sqrt(
                    func.pow(Place.latitude - filters.latitude, 2) +
                    func.pow(Place.longitude - filters.longitude, 2)
                ) * 111000 <= radius_m
            )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply sorting
        if filters.sort_by:
            if filters.sort_by == 'name':
                order_field = Place.name
            elif filters.sort_by == 'rating':
                order_field = Place.rating
            elif filters.sort_by == 'created_at':
                order_field = Place.created_at
            elif filters.sort_by == 'checkins':
                # Count check-ins for each place
                order_field = func.count(CheckIn.id)
                query = query.outerjoin(CheckIn).group_by(Place.id)
            elif filters.sort_by == 'recent_checkins':
                # Count recent check-ins (last 24 hours)
                from datetime import datetime, timedelta
                recent_time = datetime.utcnow() - timedelta(hours=24)
                order_field = func.count(CheckIn.id)
                query = query.outerjoin(CheckIn).where(
                    CheckIn.created_at >= recent_time).group_by(Place.id)
            else:
                order_field = Place.created_at

            if filters.sort_order == 'asc':
                query = query.order_by(asc(order_field))
            else:
                query = query.order_by(desc(order_field))
        else:
            # Default sorting
            query = query.order_by(desc(Place.created_at))

        # Apply pagination
        query = query.offset(filters.offset).limit(filters.limit)

        result = await db.execute(query)
        places = result.scalars().all()

        # Convert to PlaceResponse
        items = []
        for place in places:
            distance_m = None
            if filters.latitude is not None and filters.longitude is not None and place.latitude and place.longitude:
                distance_m = haversine_distance(
                    filters.latitude, filters.longitude, place.latitude, place.longitude)

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
                photo_url=_convert_single_to_signed_url(place.photo_url),
                recent_checkins_count=0,
                cross_street=place.cross_street,
                formatted_address=place.formatted_address,
                distance_meters=distance_m,
                venue_created_at=place.venue_created_at,
                primary_category=None,
                category_icons=None,
                photo_urls=_get_all_place_photos(place),
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
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    lat: float | None = Query(
        None, description="Latitude for distance sorting"),
    lng: float | None = Query(
        None, description="Longitude for distance sorting"),
    # Minimal filters
    place_type: str | None = Query(
        None, description="Place type (restaurant, cafe, etc.)"),
    cuisine: str | None = Query(
        None, description="Cuisine type (for restaurants)"),
    country: str | None = Query(None, description="Country filter"),
    city: str | None = Query(None, description="City filter"),
    neighborhood: str | None = Query(None, description="Neighborhood filter"),
    price_budget: str | None = Query(
        None, description="Price tier: $, $$, $$$"),
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

    # Validate price_budget filter
    if price_budget and price_budget not in ["$", "$$", "$$$"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid price_budget. Must be one of: $, $$, $$$"
        )

    logger.info(
        "Trending request with filters: place_type=%s, cuisine=%s, country=%s, city=%s, neighborhood=%s, price_budget=%s",
        place_type, cuisine, country, city, neighborhood, price_budget
    )

    try:
        # Convert place_type filter to Foursquare category IDs
        fsq_category_ids = None
        if place_type:
            fsq_category_ids = foursquare_filter_mapper.get_category_ids(
                place_type)
            logger.info(
                f"Mapped '{place_type}' to category IDs: {fsq_category_ids[:100] if fsq_category_ids else None}...")

        # Build Foursquare query
        fsq_query = cuisine if cuisine else None

        fsq_places = await enhanced_place_data_service.fetch_foursquare_trending(
            lat=lat,
            lon=lng,
            limit=limit,
            query=fsq_query,
            categories=fsq_category_ids,  # Pass category IDs to Foursquare
            min_price=price_tier if price_budget else None,
            max_price=price_tier if price_budget else None,
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

    # Validate price_budget filter
    if price_budget and price_budget not in ["$", "$$", "$$$"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid price_budget. Must be one of: $, $$, $$$"
        )

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
                        additional_photos_list = json.loads(
                            place.additional_photos)
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
                    photo_url=_convert_single_to_signed_url(place.photo_url),
                    recent_checkins_count=recent_count,
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

    # Apply post-filters (only for location filters not supported by Foursquare)
    # Note: place_type and price are already filtered by Foursquare API
    filtered_items = []
    for item in fsq_items:
        # Filter by location (Foursquare doesn't support these)
        if country and item.country and country.lower() not in item.country.lower():
            continue
        if city and item.city and city.lower() not in item.city.lower():
            continue
        if neighborhood and item.neighborhood and neighborhood.lower() not in item.neighborhood.lower():
            continue

        filtered_items.append(item)

    filtered_items.sort(key=lambda item: item.distance_meters or float("inf"))

    return PaginatedPlaces(
        items=filtered_items,
        total=len(filtered_items),
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
    # Minimal filters
    place_type: str | None = Query(
        None, description="Place type (restaurant, cafe, etc.)"),
    cuisine: str | None = Query(
        None, description="Cuisine type (for restaurants)"),
    country: str | None = Query(None, description="Country filter"),
    city: str | None = Query(None, description="City filter"),
    neighborhood: str | None = Query(None, description="Neighborhood filter"),
    price_budget: str | None = Query(
        None, description="Price tier: $, $$, $$$"),
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

    # Validate price_budget filter
    if price_budget and price_budget not in ["$", "$$", "$$$"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid price_budget. Must be one of: $, $$, $$$"
        )

    service = EnhancedPlaceDataService()
    places_to_use: list[Place] = []

    try:
        # Convert place_type filter to Foursquare category IDs
        fsq_category_ids = None
        if place_type:
            fsq_category_ids = foursquare_filter_mapper.get_category_ids(
                place_type)
            logger.info(
                f"Mapped '{place_type}' to category IDs: {fsq_category_ids[:100] if fsq_category_ids else None}...")

        # Convert price_budget to price tier
        price_tier = None
        if price_budget:
            price_tier = {"$": 1, "$$": 2, "$$$": 3}.get(price_budget)

        # Build Foursquare query
        fsq_query = cuisine if cuisine else None

        fsq_places = await service.fetch_foursquare_nearby(
            lat=lat,
            lon=lng,
            radius_m=radius_m,
            limit=limit,
            query=fsq_query,
            categories=fsq_category_ids,  # Pass category IDs to Foursquare
            min_price=price_tier,
            max_price=price_tier,
        )
        logger.info("Got %s places from Foursquare API", len(fsq_places))

        if not fsq_places:
            return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

        # Save places to database
        saved_places = await enhanced_place_data_service.save_foursquare_places_to_db(
            fsq_places,
            db,
        )
        await db.commit()
        places_to_use = saved_places

    except Exception as fetch_error:
        logger.error("Error fetching nearby places: %s", fetch_error)
        return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

    # Process the fetched places
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
                    photo_url=_convert_single_to_signed_url(place.photo_url),
                    recent_checkins_count=recent_count,
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

    # Apply post-filters (only for location filters not supported by Foursquare)
    # Note: place_type and price are already filtered by Foursquare API
    filtered_items = []
    for item in fsq_items:
        # Filter by location (Foursquare doesn't support these)
        if country and item.country and country.lower() not in item.country.lower():
            continue
        if city and item.city and city.lower() not in item.city.lower():
            continue
        if neighborhood and item.neighborhood and neighborhood.lower() not in item.neighborhood.lower():
            continue

        filtered_items.append(item)

    filtered_items.sort(key=lambda item: item.distance_meters or float("inf"))

    return PaginatedPlaces(
        items=filtered_items,
        total=len(filtered_items),
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
        time_limit = timedelta(hours=settings.photo_aggregation_hours)

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
                single_signed = _convert_single_to_signed_url(
                    checkin.photo_url)
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
            # TODO: Calculate actual total check-ins
            total_checkins=len(recent_checkins),
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


@router.get("/{place_id}/photos", response_model=PaginatedPhotos)
async def get_place_photos(
    place_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get photos for a specific place (check-in photos with signed URLs).

    **Authentication Required:** Yes
    """
    try:
        if place_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid place ID")

        place_query = select(Place).where(Place.id == place_id)
        place_result = await db.execute(place_query)
        place = place_result.scalar_one_or_none()

        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        total_query = (
            select(func.count(CheckInPhoto.id))
            .join(CheckIn, CheckInPhoto.check_in_id == CheckIn.id)
            .where(CheckIn.place_id == place_id, CheckInPhoto.url.isnot(None))
        )
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        photos_query = (
            select(CheckInPhoto, CheckIn)
            .join(CheckIn, CheckInPhoto.check_in_id == CheckIn.id)
            .where(CheckIn.place_id == place_id, CheckInPhoto.url.isnot(None))
            .order_by(desc(CheckInPhoto.created_at))
            .offset(offset)
            .limit(limit)
        )

        rows = await db.execute(photos_query)
        photo_rows = rows.all()

        items: list[PhotoResponse] = []
        for photo, checkin in photo_rows:
            signed_url = _convert_single_to_signed_url(photo.url)
            items.append(
                PhotoResponse(
                    id=photo.id,
                    user_id=checkin.user_id,
                    place_id=checkin.place_id,
                    review_id=None,
                    url=signed_url or photo.url,
                    caption=None,
                    created_at=photo.created_at,
                )
            )

        place_photo_candidates = _collect_place_photos(place)

        if not items and place_photo_candidates:
            fallback_urls = place_photo_candidates[offset: offset + limit]
            total = len(place_photo_candidates)
            now_ts = datetime.now(timezone.utc)
            for idx, url in enumerate(fallback_urls):
                items.append(
                    PhotoResponse(
                        id=-(idx + 1),
                        user_id=0,
                        place_id=place.id,
                        review_id=None,
                        url=url,
                        caption=None,
                        created_at=place.created_at or now_ts,
                    )
                )

        return PaginatedPhotos(
            items=items,
            total=total if items else len(place_photo_candidates),
            limit=limit,
            offset=offset,
        )

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

        if not checkins:
            return PaginatedWhosHere(
                items=[],
                total=total or 0,
                limit=limit,
                offset=offset,
            )

        checkin_ids = [checkin.id for checkin in checkins]
        place_ids = {checkin.place_id for checkin in checkins}

        photos_by_checkin: dict[int, list[str]] = {}
        if checkin_ids:
            photo_rows = await db.execute(
                select(CheckInPhoto.check_in_id, CheckInPhoto.url)
                .where(CheckInPhoto.check_in_id.in_(checkin_ids))
                .order_by(CheckInPhoto.check_in_id)
            )
            for checkin_id, url in photo_rows.all():
                if url:
                    photos_by_checkin.setdefault(checkin_id, []).append(url)

        place_photo_map: dict[int, list[str]] = {}
        if place_ids:
            place_rows = await db.execute(select(Place).where(Place.id.in_(place_ids)))
            for place in place_rows.scalars():
                place_photo_map[place.id] = _collect_place_photos(place)

        items = []
        for checkin in checkins:
            user_query = select(User).where(User.id == checkin.user_id)
            user_result = await db.execute(user_query)
            user = user_result.scalar_one_or_none()

            if not user:
                continue

            signed_photos = _convert_to_signed_urls(
                photos_by_checkin.get(checkin.id, [])
            )

            if not signed_photos and checkin.photo_url:
                single = _convert_single_to_signed_url(checkin.photo_url)
                if single:
                    signed_photos = [single]

            if not signed_photos:
                place_photos = place_photo_map.get(checkin.place_id)
                if place_photos:
                    signed_photos = place_photos[:1]

            avatar_url = _convert_single_to_signed_url(user.avatar_url)

            items.append(
                WhosHereItem(
                    check_in_id=checkin.id,
                    user_id=user.id,
                    user_name=user.name or user.username,
                    username=user.username,
                    user_avatar_url=avatar_url or user.avatar_url,
                    created_at=checkin.created_at,
                    photo_urls=signed_photos,
                )
            )

        return PaginatedWhosHere(
            items=items,
            total=total or len(items),
            limit=limit,
            offset=offset,
        )

    except Exception as e:
        logging.error(f"Error getting who's here: {e}")
        raise HTTPException(status_code=500, detail="Failed to get who's here")

# ============================================================================
# PLACE CHAT ENDPOINTS (Room chat support)
# ============================================================================


@router.get("/{place_id}/chat/room", response_model=PlaceChatRoom)
async def get_place_chat_room(
    place_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    place = await _get_place_or_404(db, place_id)
    return await _build_place_chat_room(db, place, current_user.id)


@router.post("/{place_id}/chat/join", response_model=PlaceChatRoom)
async def join_place_chat(
    place_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    place = await _get_place_or_404(db, place_id)
    await _ensure_user_can_chat(db, place_id, current_user.id)
    return await _build_place_chat_room(db, place, current_user.id)


@router.post("/{place_id}/chat/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_place_chat(
    place_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    # Chat membership is derived from check-ins; this endpoint exists for client symmetry.
    await _get_place_or_404(db, place_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{place_id}/chat/messages", response_model=PaginatedPlaceChatMessages)
async def list_place_chat_messages(
    place_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    since: Optional[str] = Query(
        None, description="Return messages created after this ISO 8601 timestamp"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    await _ensure_user_can_chat(db, place_id, current_user.id)
    filters = [PlaceChatMessage.place_id == place_id]

    window_start = datetime.now(timezone.utc) - timedelta(
        hours=int(settings.place_chat_window_hours)
    )
    filters.append(PlaceChatMessage.created_at >= window_start)

    since_dt: Optional[datetime] = None
    if since:
        since_dt = _parse_iso_datetime(since)
        filters.append(PlaceChatMessage.created_at > since_dt)

    total_query = select(func.count()).select_from(
        select(PlaceChatMessage.id).where(*filters).subquery()
    )
    total = int((await db.execute(total_query)).scalar() or 0)

    query = (
        select(PlaceChatMessage, User)
        .join(User, PlaceChatMessage.user_id == User.id)
        .where(*filters)
        .order_by(PlaceChatMessage.created_at.asc())
        .offset(offset)
        .limit(limit)
    )

    rows = await db.execute(query)
    items = [
        _serialize_place_chat_message_response(message, user)
        for message, user in rows.all()
    ]

    return PaginatedPlaceChatMessages(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{place_id}/chat/messages", response_model=PlaceChatMessageResponse)
async def create_place_chat_message(
    place_id: int,
    payload: PlaceChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(
            status_code=400, detail="Message text cannot be empty")

    place = await _get_place_or_404(db, place_id)
    await _ensure_user_can_chat(db, place_id, current_user.id)

    message = PlaceChatMessage(
        place_id=place.id,
        user_id=current_user.id,
        text=text,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    response_model = _serialize_place_chat_message_response(
        message, current_user)

    payload_dict = {
        "type": "message",
        "message": response_model.model_dump(mode="json"),
    }

    # Notify other participants in the room
    await manager.broadcast(-place_id, current_user.id, payload_dict)
    await _send_place_chat_payload_to_user(place_id, current_user.id, payload_dict)

    return response_model

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

        # Verify user exists in database (to avoid foreign key constraint errors)
        user_query = select(User).where(User.id == current_user.id)
        user_result = await db.execute(user_query)
        db_user = user_result.scalar_one_or_none()

        if not db_user:
            raise HTTPException(
                status_code=404, detail="User not found in database")

        default_vis = "public"
        check_in = CheckIn(
            user_id=current_user.id,
            place_id=payload.place_id,
            note=payload.note,
            visibility=payload.visibility or default_vis,
            expires_at=datetime.now(
                timezone.utc) + timedelta(hours=settings.checkin_expiry_hours),
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
        # Include more specific error details for debugging
        error_msg = f"Failed to create check-in: {str(e)}"
        if "foreign key constraint" in str(e).lower():
            error_msg = "User or place not found - foreign key constraint failed"
        raise HTTPException(
            status_code=500, detail=error_msg)


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
            expires_at=datetime.now(
                timezone.utc) + timedelta(hours=settings.checkin_expiry_hours),
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
        # Include more specific error details for debugging
        error_msg = f"Failed to create check-in: {str(e)}"
        if "foreign key constraint" in str(e).lower():
            error_msg = "User or place not found - foreign key constraint failed"
        raise HTTPException(
            status_code=500, detail=error_msg)


@router.delete("/check-ins/{check_in_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_check_in(
    check_in_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Delete a check-in.

    **Authentication Required:** Yes

    Only the user who created the check-in can delete it.
    """
    try:
        # Find the check-in
        checkin_query = select(CheckIn).where(CheckIn.id == check_in_id)
        checkin_result = await db.execute(checkin_query)
        checkin = checkin_result.scalar_one_or_none()

        if not checkin:
            raise HTTPException(status_code=404, detail="Check-in not found")

        # Verify ownership
        if checkin.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You can only delete your own check-ins"
            )

        # Delete associated photos first
        photos_query = select(CheckInPhoto).where(
            CheckInPhoto.check_in_id == check_in_id)
        photos_result = await db.execute(photos_query)
        photos = photos_result.scalars().all()

        for photo in photos:
            # Delete photo file from storage
            if photo.url:
                try:
                    await StorageService.delete_checkin_photo(check_in_id, photo.url)
                except Exception as e:
                    logger.warning(
                        f"Failed to delete photo file {photo.url}: {e}")
            # Delete photo record
            await db.delete(photo)

        # Delete the check-in
        await db.delete(checkin)
        await db.commit()

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete check-in {check_in_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete check-in: {str(e)}"
        )

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

        saved_place = await ensure_saved_place_entry(
            db,
            current_user.id,
            payload.place_id,
            desired_name,
        )
        # Ensure the SavedPlace has a linked collection ID
        if saved_place.collection_id is None:
            if saved_place.collection is not None:
                saved_place.collection_id = saved_place.collection.id
            else:
                collection_row = await db.execute(
                    select(UserCollection.id, UserCollection.name)
                    .where(
                        and_(
                            UserCollection.user_id == current_user.id,
                            func.lower(UserCollection.name)
                            == desired_name.lower(),
                        )
                    )
                    .limit(1)
                )
                collection = collection_row.first()
                if collection:
                    saved_place.collection_id = collection.id
                    saved_place.list_name = collection.name

        await db.commit()
        await db.refresh(saved_place)

        collection_name = saved_place.list_name
        if saved_place.collection_id:
            name_row = await db.execute(
                select(UserCollection.name).where(
                    UserCollection.id == saved_place.collection_id
                )
            )
            fetched_name = name_row.scalar_one_or_none()
            if fetched_name:
                collection_name = fetched_name

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
        logging.error("Error saving place: %s", e)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save place: {e}",
        )


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
            filters.append(func.lower(UserCollection.name)
                           == normalized_name.lower())

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
