import hashlib
import json

from ..models import Follow
from ..routers.activity import create_checkin_activity
from ..utils import can_view_checkin, haversine_distance
from ..services.place_data_service_v2 import enhanced_place_data_service
from ..services.storage import StorageService
from ..services.jwt_service import JWTService
from ..schemas import (
    PlaceCreate,
    PlaceResponse,
    CheckInCreate,
    CheckInResponse,
    # for check-in photo upload

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
)
from ..models import Place, CheckIn, SavedPlace, User, Review, Photo, CheckInPhoto, ExternalSearchSnapshot
from ..dependencies import get_current_admin_user
from ..database import get_db
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, text, or_, and_, literal
from sqlalchemy.exc import SQLAlchemyError
import httpx
import logging
from math import cos, radians

# Configure logging
logger = logging.getLogger(__name__)


def _convert_to_signed_urls(photo_urls: list[str]) -> list[str]:
    """
    Convert S3 keys to signed URLs for secure access.
    """
    signed_urls = []
    for url in photo_urls:
        if url and not url.startswith('http'):
            # This is an S3 key, convert to signed URL
            try:
                signed_url = StorageService.generate_signed_url(url)
                signed_urls.append(signed_url)
            except Exception as e:
                logger.error(f"Failed to generate signed URL for {url}: {e}")
                # Fallback to original URL if signing fails
                signed_urls.append(url)
        else:
            # Already a full URL (e.g., from FSQ or local storage)
            signed_urls.append(url)
    return signed_urls


def _convert_single_to_signed_url(photo_url: str | None) -> str | None:
    """
    Convert a single S3 key or S3 URL to signed URL for secure access.
    """
    if not photo_url:
        return None

    if not photo_url.startswith('http'):
        # This is an S3 key, convert to signed URL
        try:
            return StorageService.generate_signed_url(photo_url)
        except Exception as e:
            logger.error(f"Failed to generate signed URL for {photo_url}: {e}")
            # Fallback to original URL if signing fails
            return photo_url
    elif 's3.amazonaws.com' in photo_url or 'circles-media-259c' in photo_url:
        # This is an S3 URL, extract the key and convert to signed URL
        try:
            # Extract S3 key from URL like: https://circles-media-259c.s3.amazonaws.com/checkins/39/test_photo.jpg
            # or: https://s3.amazonaws.com/circles-media-259c/checkins/39/test_photo.jpg
            if 's3.amazonaws.com' in photo_url:
                # Handle both path-style and virtual-hosted-style URLs
                if '/circles-media-259c/' in photo_url:
                    # Path-style: https://s3.amazonaws.com/circles-media-259c/checkins/39/test_photo.jpg
                    s3_key = photo_url.split('/circles-media-259c/')[1]
                else:
                    # Virtual-hosted-style: https://circles-media-259c.s3.amazonaws.com/checkins/39/test_photo.jpg
                    s3_key = photo_url.split('.s3.amazonaws.com/')[1]

                return StorageService.generate_signed_url(s3_key)
            else:
                # Fallback for other S3 URLs
                return photo_url
        except Exception as e:
            logger.error(
                f"Failed to generate signed URL from S3 URL {photo_url}: {e}")
            # Fallback to original URL if signing fails
            return photo_url
    else:
        # Already a full URL (e.g., from FSQ or local storage)
        return photo_url


def _build_external_search_key(
    lat: float,
    lon: float,
    radius: int,
    query: str | None,
    types: list[str] | None,
) -> str:
    """Deterministic key for grouping external search snapshots."""

    payload = {
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "radius": radius,
        "query": (query or "").strip().lower(),
        "types": tuple(sorted(t.strip().lower() for t in types or [])),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


router = APIRouter(
    prefix="/places",
    tags=["places"],
    responses={
        404: {"description": "Place not found"},
        400: {"description": "Invalid request data"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"}
    }
)


async def _nearby_places_python_fallback(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_m: int,
    limit: int,
    offset: int,
) -> PaginatedPlaces:
    """Fallback nearby query for databases without PostGIS/math functions."""
    lat_buffer = radius_m / 111_320
    cos_lat = cos(radians(lat))
    # Avoid division by zero near the poles
    if abs(cos_lat) < 1e-6:
        lon_buffer = 180
    else:
        lon_buffer = radius_m / (111_320 * abs(cos_lat))

    min_lat = max(lat - lat_buffer, -90)
    max_lat = min(lat + lat_buffer, 90)
    min_lng = lng - lon_buffer
    max_lng = lng + lon_buffer

    stmt = select(Place).where(
        Place.latitude.is_not(None),
        Place.longitude.is_not(None),
        Place.latitude >= min_lat,
        Place.latitude <= max_lat,
    )

    # Only apply longitude bounds when we are not spanning the entire globe
    if lon_buffer < 180:
        min_lng = max(min_lng, -180)
        max_lng = min(max_lng, 180)
        stmt = stmt.where(Place.longitude >= min_lng,
                          Place.longitude <= max_lng)

    candidates = (await db.execute(stmt)).scalars().all()

    within_radius: list[tuple[float, Place]] = []
    for place in candidates:
        if place.latitude is None or place.longitude is None:
            continue
        distance_m = haversine_distance(
            lat, lng, place.latitude, place.longitude) * 1000
        if distance_m <= radius_m:
            within_radius.append((distance_m, place))

    within_radius.sort(key=lambda item: item[0])

    total = len(within_radius)
    sliced = within_radius[offset: offset + limit]
    items = [place for _, place in sliced]

    return PaginatedPlaces(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        external_results=[],
        external_count=0,
    )


@router.get("/lookups/countries", response_model=list[str])
async def lookup_countries(db: AsyncSession = Depends(get_db)):
    # First, get existing countries from places table
    res = await db.execute(select(func.distinct(Place.country)).where(Place.country.is_not(None)).order_by(Place.country.asc()))
    countries = [r[0] for r in res.all() if r[0]]

    # If we have very few countries, try to populate some missing data
    if len(countries) < 5:
        # Get up to 20 places missing country data but have coordinates
        places_missing_country = await db.execute(
            select(Place).where(
                Place.country.is_(None),
                Place.latitude.is_not(None),
                Place.longitude.is_not(None)
            ).limit(20)
        )
        places_to_update = places_missing_country.scalars().all()

        # Populate country data for some places using reverse geocoding
        for place in places_to_update:
            try:
                geo = await enhanced_place_data_service.reverse_geocode_details(
                    lat=place.latitude,
                    lon=place.longitude
                )
                if geo.get("country"):
                    place.country = geo.get("country")
                    # Also populate city and neighborhood if missing
                    if geo.get("city") and not place.city:
                        place.city = geo.get("city")
                    if geo.get("neighborhood") and not place.neighborhood:
                        place.neighborhood = geo.get("neighborhood")
            except Exception:
                # Skip if geocoding fails, continue with other places
                continue

        # Commit updates and re-query countries
        await db.commit()
        res = await db.execute(select(func.distinct(Place.country)).where(Place.country.is_not(None)).order_by(Place.country.asc()))
        countries = [r[0] for r in res.all() if r[0]]

    return countries


@router.get("/lookups/cities", response_model=list[str])
async def lookup_cities(country: str | None = Query(None), db: AsyncSession = Depends(get_db)):
    stmt = select(func.distinct(Place.city)).where(Place.city.is_not(None))
    if country:
        stmt = stmt.where(Place.country.ilike(country))
    stmt = stmt.order_by(Place.city.asc())
    res = await db.execute(stmt)
    return [r[0] for r in res.all() if r[0]]


@router.get("/lookups/neighborhoods", response_model=list[str])
async def lookup_neighborhoods(country: str, city: str, db: AsyncSession = Depends(get_db)):
    stmt = select(func.distinct(Place.neighborhood)).where(
        Place.neighborhood.is_not(None),
        Place.city.ilike(city),
        Place.country.ilike(country),
    ).order_by(Place.neighborhood.asc())
    res = await db.execute(stmt)
    return [r[0] for r in res.all() if r[0]]


@router.post("/", response_model=PlaceResponse)
async def create_place(payload: PlaceCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new place in the system.

    **Authentication Required:** No (public endpoint)

    **Features:**
    - Creates a new place with location data
    - Supports PostGIS integration for geospatial queries
    - Normalizes categories to comma-separated format

    **Location Data:**
    - `latitude`/`longitude`: Required for proximity features
    - PostGIS geography column is automatically set if enabled

    **Categories:**
    - Can be provided as list or string
    - Automatically normalized to comma-separated format
    - Used for search and filtering

    **Use Cases:**
    - Add new businesses/venues to the platform
    - Enable check-ins at new locations
    - Expand place database
    """
    # Normalize categories to comma-separated string
    categories = None
    if payload.categories is not None:
        if isinstance(payload.categories, list):
            categories = ",".join([c.strip() for c in payload.categories])
        else:
            categories = str(payload.categories)
    place = Place(
        name=payload.name,
        address=payload.address,
        city=payload.city,
        neighborhood=payload.neighborhood,
        latitude=payload.latitude,
        longitude=payload.longitude,
        categories=categories,
        rating=payload.rating,
    )
    db.add(place)
    await db.commit()
    await db.refresh(place)
    # If PostGIS enabled and lat/lng present, set geography
    from ..config import settings as app_settings
    if app_settings.use_postgis and place.latitude is not None and place.longitude is not None:
        place_id = place.id
        try:
            await db.execute(
                text(
                    (
                        "UPDATE places SET location = ST_SetSRID("
                        "ST_MakePoint(:lng, :lat), 4326)::geography WHERE id = :id"
                    )
                ),
                {"lng": place.longitude, "lat": place.latitude, "id": place.id},
            )
            await db.commit()
        except SQLAlchemyError as exc:  # pragma: no cover - only triggered without PostGIS
            await db.rollback()
            try:
                await db.refresh(place)
            except SQLAlchemyError:
                pass
            logging.warning(
                "Skipping PostGIS location update for place %s: %s",
                place_id,
                exc,
            )
    # Auto-populate country/city/neighborhood if missing using reverse geocoding
    if place.latitude is not None and place.longitude is not None:
        try:
            geo = await enhanced_place_data_service.reverse_geocode_details(lat=place.latitude, lon=place.longitude)
            updated = False
            if not getattr(place, "country", None) and geo.get("country"):
                place.country = geo.get("country")
                updated = True
            if not place.city and geo.get("city"):
                place.city = geo.get("city")
                updated = True
            if not place.neighborhood and geo.get("neighborhood"):
                place.neighborhood = geo.get("neighborhood")
                updated = True
            if updated:
                await db.commit()
                await db.refresh(place)
        except Exception:
            pass
    return place


@router.get("/search", response_model=PaginatedPlaces)
async def search_places(
    query: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    category: str | None = None,
    rating_min: float | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for places with basic filters.

    **Authentication Required:** No (public endpoint)

    **Search Filters:**
    - `query`: Search in place names (partial match)
    - `city`: Filter by specific city
    - `neighborhood`: Filter by neighborhood
    - `category`: Filter by category (partial match)
    - `rating_min`: Minimum rating filter

    **Pagination:**
    - `limit`: Number of results (1-100, default 20)
    - `offset`: Number of results to skip (default 0)

    **Response:**
    - `items`: Array of places matching criteria
    - `total`: Total number of matching places
    - `limit`/`offset`: Pagination info

    **Use Cases:**
    - Basic place discovery
    - Location-based searches
    - Category browsing
    - Rating-based filtering
    """
    # total count
    count_stmt = select(func.count(Place.id))
    if query:
        count_stmt = count_stmt.where(Place.name.ilike(f"%{query}%"))
    if city:
        count_stmt = count_stmt.where(Place.city == city)
    if neighborhood:
        count_stmt = count_stmt.where(Place.neighborhood == neighborhood)
    if category:
        count_stmt = count_stmt.where(Place.categories.ilike(f"%{category}%"))
    if rating_min is not None:
        count_stmt = count_stmt.where(Place.rating >= rating_min)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = select(Place)
    if query:
        stmt = stmt.where(Place.name.ilike(f"%{query}%"))
    if city:
        stmt = stmt.where(Place.city == city)
    if neighborhood:
        stmt = stmt.where(Place.neighborhood == neighborhood)
    if category:
        stmt = stmt.where(Place.categories.ilike(f"%{category}%"))
    if rating_min is not None:
        stmt = stmt.where(Place.rating >= rating_min)
    stmt = stmt.offset(offset).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
    return PaginatedPlaces(items=items, total=total, limit=limit, offset=offset)


@router.get("/recommendations", response_model=PaginatedPlaces)
async def get_recommendations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get personalized place recommendations.

    **Authentication Required:** Yes

    **Recommendation Algorithm:**
    - Based on followed users' recent check-ins (7 days)
    - Considers followed users' reviews (30 days)
    - Boosts places matching user interests
    - Optional geo-reranking by proximity

    **Parameters:**
    - `lat`/`lng`: Optional coordinates for proximity re-ranking
    - `limit`/`offset`: Standard pagination

    **Scoring:**
    - Check-ins from followed users: 5 points each
    - Reviews from followed users: 3 points each
    - Interest matches: 1 point per match

    **Use Cases:**
    - Personalized place discovery
    - Social recommendations
    - Interest-based suggestions
    - Location-aware recommendations
    """
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    # Get followed users
    followed_subq = select(Follow.followee_id).where(
        Follow.follower_id == current_user.id
    ).subquery()

    # Counts for followed users' recent check-ins and reviews
    checkins_subq = (
        select(CheckIn.place_id, func.count(CheckIn.id).label("c"))
        .where(CheckIn.user_id.in_(select(followed_subq.c.followee_id)), CheckIn.created_at >= seven_days_ago)
        .group_by(CheckIn.place_id)
        .subquery()
    )
    reviews_subq = (
        select(Review.place_id, func.count(Review.id).label("r"))
        .where(Review.user_id.in_(select(followed_subq.c.followee_id)), Review.created_at >= thirty_days_ago)
        .group_by(Review.place_id)
        .subquery()
    )

    # User interests
    from ..models import UserInterest
    interests_rows = (await db.execute(select(UserInterest.name).where(UserInterest.user_id == current_user.id))).all()
    interest_terms = [row[0] for row in interests_rows]

    # Base score
    score_expr = (
        func.coalesce(checkins_subq.c.c, 0) * 5 +
        func.coalesce(reviews_subq.c.r, 0) * 3
    )

    # Interest boost expression built inline to avoid alias issues
    from sqlalchemy import literal
    interest_boost_expr = literal(0)
    for term in (interest_terms or []):
        interest_boost_expr = interest_boost_expr + func.case(
            (Place.categories.ilike(f"%{term}%"), 1), else_=0
        )

    total_score_expr = score_expr + interest_boost_expr

    stmt = (
        select(Place)
        .join(checkins_subq, Place.id == checkins_subq.c.place_id, isouter=True)
        .join(reviews_subq, Place.id == reviews_subq.c.place_id, isouter=True)
        .order_by(desc(total_score_expr))
        .offset(offset)
        .limit(limit)
    )

    # Execute queries
    total = (await db.execute(select(func.count()).select_from(checkins_subq))).scalar_one()
    items = (await db.execute(stmt)).scalars().all()

    # Optional: re-rank by proximity if coordinates provided
    if lat is not None and lng is not None:
        from ..utils import haversine_distance

        def distance_or_inf(p: Place) -> float:
            if p.latitude is None or p.longitude is None:
                return float("inf")
            return haversine_distance(lat, lng, p.latitude, p.longitude)
        items = sorted(items, key=distance_or_inf)

    return PaginatedPlaces(items=items, total=total, limit=limit, offset=offset)


@router.post("/search/advanced", response_model=PaginatedPlaces)
async def advanced_search_places(
    filters: AdvancedSearchFilters,
    db: AsyncSession = Depends(get_db),
):
    """Advanced search with multiple filters, sorting, and distance-based search"""

    # Build base query
    stmt = select(Place)
    count_stmt = select(func.count(Place.id))

    # Text search
    if filters.query:
        query_filter = Place.name.ilike(f"%{filters.query}%")
        stmt = stmt.where(query_filter)
        count_stmt = count_stmt.where(query_filter)

    # Location filters
    if filters.city:
        city_filter = Place.city.ilike(f"%{filters.city}%")
        stmt = stmt.where(city_filter)
        count_stmt = count_stmt.where(city_filter)

    if filters.neighborhood:
        neighborhood_filter = Place.neighborhood.ilike(
            f"%{filters.neighborhood}%")
        stmt = stmt.where(neighborhood_filter)
        count_stmt = count_stmt.where(neighborhood_filter)

    # Category filters (support multiple categories)
    if filters.categories:
        category_conditions = []
        for category in filters.categories:
            category_conditions.append(Place.categories.ilike(f"%{category}%"))
        if category_conditions:
            category_filter = or_(*category_conditions)
            stmt = stmt.where(category_filter)
            count_stmt = count_stmt.where(category_filter)

    # Rating filters
    if filters.rating_min is not None:
        rating_min_filter = Place.rating >= filters.rating_min
        stmt = stmt.where(rating_min_filter)
        count_stmt = count_stmt.where(rating_min_filter)

    if filters.rating_max is not None:
        rating_max_filter = Place.rating <= filters.rating_max
        stmt = stmt.where(rating_max_filter)
        count_stmt = count_stmt.where(rating_max_filter)

    # Activity filters
    if filters.has_recent_checkins is not None:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        recent_checkins_subq = (
            select(CheckIn.place_id)
            .where(CheckIn.created_at >= yesterday)
            .group_by(CheckIn.place_id)
            .subquery()
        )
        if filters.has_recent_checkins:
            stmt = stmt.where(Place.id.in_(
                select(recent_checkins_subq.c.place_id)))
            count_stmt = count_stmt.where(Place.id.in_(
                select(recent_checkins_subq.c.place_id)))
        else:
            stmt = stmt.where(~Place.id.in_(
                select(recent_checkins_subq.c.place_id)))
            count_stmt = count_stmt.where(~Place.id.in_(
                select(recent_checkins_subq.c.place_id)))

    if filters.has_reviews is not None:
        reviews_subq = (
            select(Review.place_id)
            .group_by(Review.place_id)
            .subquery()
        )
        if filters.has_reviews:
            stmt = stmt.where(Place.id.in_(select(reviews_subq.c.place_id)))
            count_stmt = count_stmt.where(
                Place.id.in_(select(reviews_subq.c.place_id)))
        else:
            stmt = stmt.where(~Place.id.in_(select(reviews_subq.c.place_id)))
            count_stmt = count_stmt.where(
                ~Place.id.in_(select(reviews_subq.c.place_id)))

    if filters.has_photos is not None:
        photos_subq = (
            select(Photo.place_id)
            .where(Photo.review_id.is_not(None))
            .group_by(Photo.place_id)
            .subquery()
        )
        if filters.has_photos:
            stmt = stmt.where(Place.id.in_(select(photos_subq.c.place_id)))
            count_stmt = count_stmt.where(
                Place.id.in_(select(photos_subq.c.place_id)))
        else:
            stmt = stmt.where(~Place.id.in_(select(photos_subq.c.place_id)))
            count_stmt = count_stmt.where(
                ~Place.id.in_(select(photos_subq.c.place_id)))

    # Distance-based search (if coordinates provided)
    if filters.latitude is not None and filters.longitude is not None and filters.radius_km is not None:
        from ..config import settings as app_settings
        if app_settings.use_postgis:
            # Use PostGIS for efficient distance search
            point = func.ST_SetSRID(func.ST_MakePoint(
                filters.longitude, filters.latitude), 4326)
            place_point = func.ST_SetSRID(func.ST_MakePoint(
                Place.longitude, Place.latitude), 4326)
            distance_filter = func.ST_DWithin(
                place_point.cast(text('geography')),
                point.cast(text('geography')),
                filters.radius_km * 1000  # Convert km to meters
            )
            stmt = stmt.where(distance_filter)
            count_stmt = count_stmt.where(distance_filter)
        else:
            # Fallback to Haversine formula - distance filtering will be applied after query
            # This ensures distance filtering works even without PostGIS
            logger.info(
                "Using fallback distance filtering (PostGIS not available)")

    # Sorting
    if filters.sort_by:
        sort_column = getattr(Place, filters.sort_by, Place.name)
        if filters.sort_by == "checkins":
            # Sort by total check-ins count
            checkins_subq = (
                select(CheckIn.place_id, func.count(
                    CheckIn.id).label('checkin_count'))
                .group_by(CheckIn.place_id)
                .subquery()
            )
            stmt = stmt.outerjoin(checkins_subq, Place.id ==
                                  checkins_subq.c.place_id)
            sort_column = func.coalesce(checkins_subq.c.checkin_count, 0)
        elif filters.sort_by == "recent_checkins":
            # Sort by recent check-ins count
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            recent_checkins_subq = (
                select(CheckIn.place_id, func.count(
                    CheckIn.id).label('recent_count'))
                .where(CheckIn.created_at >= yesterday)
                .group_by(CheckIn.place_id)
                .subquery()
            )
            stmt = stmt.outerjoin(recent_checkins_subq,
                                  Place.id == recent_checkins_subq.c.place_id)
            sort_column = func.coalesce(recent_checkins_subq.c.recent_count, 0)

        if filters.sort_order == "desc":
            stmt = stmt.order_by(sort_column.desc())
        else:
            stmt = stmt.order_by(sort_column.asc())
    else:
        # Default sorting by name
        stmt = stmt.order_by(Place.name.asc())

    # Pagination
    stmt = stmt.offset(filters.offset).limit(filters.limit)

    # Execute queries
    total = (await db.execute(count_stmt)).scalar_one()
    places = (await db.execute(stmt)).scalars().all()

    # Attach FSQ photo if available in place_metadata
    items: list[PlaceResponse] = []
    for p in places:
        photo_url = None
        md = getattr(p, 'place_metadata', None) or {}
        photos = md.get('photos') or []
        if photos:
            first = photos[0]
            photo_url = first if isinstance(first, str) else first.get('url')
        items.append(PlaceResponse(
            id=p.id,
            name=p.name,
            address=p.address,
            country=getattr(p, 'country', None),
            city=p.city,
            neighborhood=p.neighborhood,
            latitude=p.latitude,
            longitude=p.longitude,
            categories=p.categories,
            rating=p.rating,
            description=getattr(p, 'description', None),
            created_at=p.created_at,
            photo_url=photo_url,
        ))

    # Apply distance filtering for non-PostGIS fallback
    if (filters.latitude is not None and filters.longitude is not None and
            filters.radius_km is not None):
        from ..config import settings as app_settings_fallback
        if not getattr(app_settings_fallback, 'use_postgis', False):
            from ..utils import haversine_distance
            filtered_items = []
            for place in items:
                if place.latitude and place.longitude:
                    distance = haversine_distance(
                        filters.latitude, filters.longitude,
                        place.latitude, place.longitude
                    )
                    if distance <= filters.radius_km:
                        filtered_items.append(place)
            items = filtered_items
            total = len(filtered_items)  # This is approximate for pagination

    return PaginatedPlaces(items=items, total=total, limit=filters.limit, offset=filters.offset)


@router.get("/search/suggestions", response_model=SearchSuggestions)
async def get_search_suggestions(
    query: str | None = None,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get search suggestions for cities, neighborhoods, and categories"""

    # City suggestions
    city_stmt = select(Place.city, func.count(Place.id).label('count'))
    if query:
        city_stmt = city_stmt.where(Place.city.ilike(f"%{query}%"))
    city_stmt = city_stmt.where(Place.city.is_not(None)).group_by(
        Place.city).order_by(desc('count')).limit(limit)
    city_results = (await db.execute(city_stmt)).all()

    # Neighborhood suggestions
    neighborhood_stmt = select(
        Place.neighborhood, func.count(Place.id).label('count'))
    if query:
        neighborhood_stmt = neighborhood_stmt.where(
            Place.neighborhood.ilike(f"%{query}%"))
    neighborhood_stmt = neighborhood_stmt.where(Place.neighborhood.is_not(
        None)).group_by(Place.neighborhood).order_by(desc('count')).limit(limit)
    neighborhood_results = (await db.execute(neighborhood_stmt)).all()

    # Category suggestions (extract from comma-separated categories)
    category_stmt = select(
        Place.categories, func.count(Place.id).label('count'))
    if query:
        category_stmt = category_stmt.where(
            Place.categories.ilike(f"%{query}%"))
    category_stmt = category_stmt.where(Place.categories.is_not(None)).group_by(Place.categories).order_by(
        # Get more to extract individual categories
        desc('count')).limit(limit * 2)
    category_results = (await db.execute(category_stmt)).all()

    # Process categories (split comma-separated values)
    category_counts = {}
    for result in category_results:
        if result.categories:
            categories = [cat.strip() for cat in result.categories.split(',')]
            for category in categories:
                if category and (not query or query.lower() in category.lower()):
                    category_counts[category] = category_counts.get(
                        category, 0) + result.count

    # Sort categories by count and take top results
    sorted_categories = sorted(
        category_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

    return SearchSuggestions(
        cities=[SearchSuggestion(
            type="city", value=result.city, count=result.count) for result in city_results],
        neighborhoods=[SearchSuggestion(
            type="neighborhood", value=result.neighborhood, count=result.count) for result in neighborhood_results],
        categories=[SearchSuggestion(type="category", value=category, count=count)
                    for category, count in sorted_categories]
    )


@router.get("/search/filter-options")
async def get_filter_options(db: AsyncSession = Depends(get_db)):
    """Get available filter options for search"""

    # Get all cities
    cities_stmt = select(Place.city, func.count(Place.id).label('count')).where(
        Place.city.is_not(None)).group_by(Place.city).order_by(desc('count'))
    cities = (await db.execute(cities_stmt)).all()

    # Get all neighborhoods
    neighborhoods_stmt = select(Place.neighborhood, func.count(Place.id).label('count')).where(
        Place.neighborhood.is_not(None)).group_by(Place.neighborhood).order_by(desc('count'))
    neighborhoods = (await db.execute(neighborhoods_stmt)).all()

    # Get all categories
    categories_stmt = select(Place.categories, func.count(Place.id).label('count')).where(
        Place.categories.is_not(None)).group_by(Place.categories).order_by(desc('count'))
    categories_results = (await db.execute(categories_stmt)).all()

    # Process categories
    category_counts = {}
    for result in categories_results:
        if result.categories:
            categories = [cat.strip() for cat in result.categories.split(',')]
            for category in categories:
                if category:
                    category_counts[category] = category_counts.get(
                        category, 0) + result.count

    # Get rating range
    rating_stats = (await db.execute(select(func.min(Place.rating), func.max(Place.rating), func.avg(Place.rating)))).first()

    return {
        "cities": [{"name": city.city, "count": city.count} for city in cities],
        "neighborhoods": [{"name": neighborhood.neighborhood, "count": neighborhood.count} for neighborhood in neighborhoods],
        "categories": [{"name": category, "count": count} for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True)],
        "rating_range": {
            "min": float(rating_stats[0]) if rating_stats[0] else 0,
            "max": float(rating_stats[1]) if rating_stats[1] else 5,
            "average": float(rating_stats[2]) if rating_stats[2] else 0
        }
    }


@router.get("/search/quick", response_model=PaginatedPlaces)
async def quick_search_places(
    q: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Quick search across multiple fields (name, city, neighborhood, categories)"""

    # Build search query across multiple fields
    search_conditions = [
        Place.name.ilike(f"%{q}%"),
        Place.city.ilike(f"%{q}%"),
        Place.neighborhood.ilike(f"%{q}%"),
        Place.categories.ilike(f"%{q}%")
    ]

    # Count total
    count_stmt = select(func.count(Place.id)).where(
        or_(*search_conditions))
    total = (await db.execute(count_stmt)).scalar_one()

    # Get results
    stmt = select(Place).where(or_(*search_conditions)
                               ).order_by(Place.name.asc()).offset(offset).limit(limit)
    items = (await db.execute(stmt)).scalars().all()

    return PaginatedPlaces(items=items, total=total, limit=limit, offset=offset)


# Removed place-level photo upload; use review-attached photos instead
# Review photos

@router.post("/reviews/{review_id}/photos", response_model=PhotoResponse)
async def add_review_photo(
    review_id: int,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ensure review exists and owner is current user
    res = await db.execute(select(Review).where(Review.id == review_id))
    review = res.scalars().first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not allowed to add photo to this review")

    import os
    from uuid import uuid4
    _, ext = os.path.splitext(file.filename or "")
    if not ext:
        ext = ".jpg"
    filename = f"{uuid4().hex}{ext}"
    content = await file.read()
    try:
        url_path = await StorageService.save_review_photo(review_id, filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    photo = Photo(
        user_id=current_user.id,
        place_id=review.place_id,
        review_id=review_id,
        url=url_path,
        caption=caption,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    # Convert S3 key to signed URL for response
    signed_url = _convert_single_to_signed_url(photo.url)
    photo.url = signed_url

    return photo


@router.get("/{place_id}/photos", response_model=PaginatedPhotos)
async def list_review_photos_for_place(
    place_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get all photos for a place (from reviews)"""
    # Verify place exists
    res = await db.execute(select(Place).where(Place.id == place_id))
    place = res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Only photos attached to reviews for this place
    total_q = select(func.count(Photo.id)).where(
        Photo.place_id == place_id, Photo.review_id.is_not(None))
    total = (await db.execute(total_q)).scalar_one()
    stmt = (
        select(Photo)
        .where(Photo.place_id == place_id, Photo.review_id.is_not(None))
        .order_by(Photo.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = (await db.execute(stmt)).scalars().all()

    # Convert S3 keys to signed URLs for all photos
    for photo in items:
        photo.url = _convert_single_to_signed_url(photo.url)

    return PaginatedPhotos(items=items, total=total, limit=limit, offset=offset)


@router.get("/{place_id}/reviews", response_model=PaginatedReviews)
async def list_place_reviews(
    place_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get all reviews for a place"""
    # Verify place exists
    res = await db.execute(select(Place).where(Place.id == place_id))
    place = res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Count total reviews
    total_q = select(func.count(Review.id)).where(Review.place_id == place_id)
    total = (await db.execute(total_q)).scalar_one()

    # Get reviews with user info
    stmt = (
        select(Review)
        .where(Review.place_id == place_id)
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = (await db.execute(stmt)).scalars().all()
    return PaginatedReviews(items=items, total=total, limit=limit, offset=offset)


@router.delete("/reviews/{review_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review_photo(
    review_id: int,
    photo_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.review_id == review_id))
    photo = res.scalars().first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not allowed to delete this photo")
    # Try to delete underlying file (best-effort)
    try:
        # extract filename from URL path
        import os
        filename = os.path.basename(photo.url)
        await StorageService.delete_review_photo(review_id, filename)
    except Exception:
        pass
    await db.delete(photo)
    await db.commit()
    return None


# Removed place-level photo listing; list via reviews endpoint instead


# Removed delete via place; use delete via review route


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
    Get trending places based on recent activity.

    **Authentication Required:** No

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

    **Parameters:**
    - `time_window`: Activity time period
    - `lat`/`lng`: Optional coordinates for proximity re-ranking
    - `limit`/`offset`: Standard pagination

    **Use Cases:**
    - Discover popular places
    - Real-time trending content
    - Location-aware trending
    - Activity-based discovery
    """
    # Require coordinates for local trending
    if lat is None or lng is None:
        raise HTTPException(
            status_code=400, detail="lat and lng are required for local trending")

    # Derive geo details via reverse geocoding (Nominatim)
    geo = await enhanced_place_data_service.reverse_geocode_details(lat=lat, lon=lng)
    inferred_city = city or geo.get("city")
    inferred_neighborhood = geo.get("neighborhood")

    # FSQ override: use Foursquare-based trending by inferred city if enabled
    from ..config import settings as app_settings
    if app_settings.fsq_trending_override:
        # Prefer explicit city, else inferred; fallback to lat/lng search
        if inferred_city:
            fsq = await enhanced_place_data_service.fetch_foursquare_trending_city(city=inferred_city, limit=limit)
        else:
            fsq = await enhanced_place_data_service.fetch_foursquare_trending(lat=lat, lon=lng, limit=limit)
        now_ts = datetime.now(timezone.utc)
        # Optionally attach a best-effort photo if present in metadata
        items = []
        for idx, p in enumerate(fsq):
            photo_url = None
            md = p.get("metadata") or {}
            photos = md.get("photos") or []
            if photos and isinstance(photos, list):
                # photos may be URL strings or dicts with url
                first = photos[0]
                photo_url = first if isinstance(
                    first, str) else first.get("url")
            items.append(
                PlaceResponse(
                    id=-(idx + 1),
                    name=p.get("name"),
                    address=None,
                    city=inferred_city,
                    neighborhood=None,
                    latitude=p.get("latitude"),
                    longitude=p.get("longitude"),
                    categories=p.get("categories"),
                    rating=p.get("rating"),
                    created_at=now_ts,
                    photo_url=photo_url,
                )
            )
        # client-side like filters server-applied on FSQ set
        if q:
            items = [it for it in items if it.name and q.lower()
                     in it.name.lower()]
        if place_type:
            items = [it for it in items if it.categories and place_type.lower() in str(
                it.categories).lower()]
        if min_rating is not None:
            items = [it for it in items if (it.rating or 0) >= min_rating]
        return PaginatedPlaces(items=items, total=len(items), limit=limit, offset=offset)

    # Calculate time window
    now = datetime.now(timezone.utc)
    time_windows = {
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(days=1),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }

    if time_window not in time_windows:
        raise HTTPException(
            status_code=400, detail="Invalid time window. Use: 1h, 6h, 24h, 7d, 30d")

    window_start = now - time_windows[time_window]

    if not inferred_city:
        raise HTTPException(
            status_code=404, detail="Could not infer city from provided coordinates")

    # Build trending score query filtered by inferred city
    # Score = (check-ins * 3) + (reviews * 2) + (photos * 1) + (unique users * 2)
    trending_base = (
        select(
            Place.id,
            Place.name,
            Place.address,
            Place.city,
            Place.neighborhood,
            Place.latitude,
            Place.longitude,
            Place.categories,
            Place.rating,
            Place.created_at,
            # Check-ins count
            func.coalesce(func.count(CheckIn.id), 0).label('checkins_count'),
            # Reviews count
            func.coalesce(func.count(Review.id), 0).label('reviews_count'),
            # Photos count (from reviews)
            func.coalesce(func.count(Photo.id), 0).label('photos_count'),
            # Unique users who checked in
            func.coalesce(func.count(func.distinct(CheckIn.user_id)), 0).label(
                'unique_users'),
            # Calculate trending score
            (
                func.coalesce(func.count(CheckIn.id), 0) * 3 +
                func.coalesce(func.count(Review.id), 0) * 2 +
                func.coalesce(func.count(Photo.id), 0) * 1 +
                func.coalesce(func.count(
                    func.distinct(CheckIn.user_id)), 0) * 2
            ).label('trending_score')
        )
        .outerjoin(CheckIn, and_(
            Place.id == CheckIn.place_id,
            CheckIn.created_at >= window_start
        ))
        .outerjoin(Review, and_(
            Place.id == Review.place_id,
            Review.created_at >= window_start
        ))
        .outerjoin(Photo, and_(
            Review.id == Photo.review_id,
            Photo.created_at >= window_start
        ))
    )

    # Apply location filters: prefer explicit params, else inferred city
    if country:
        trending_base = trending_base.where(Place.country.ilike(country))
    if inferred_city:
        trending_base = trending_base.where(Place.city.ilike(inferred_city))
    # Only narrow by neighborhood if explicitly provided
    if neighborhood:
        trending_base = trending_base.where(
            Place.neighborhood.ilike(f"%{neighborhood}%"))
    if q:
        trending_base = trending_base.where(Place.name.ilike(f"%{q}%"))
    if place_type:
        trending_base = trending_base.where(
            Place.categories.ilike(f"%{place_type}%"))
    if neighborhood:
        trending_base = trending_base.where(
            Place.neighborhood.ilike(f"%{neighborhood}%"))
    if min_rating is not None:
        trending_base = trending_base.where(Place.rating >= min_rating)
    if price_tier:
        trending_base = trending_base.where(Place.price_tier == price_tier)

    trending_subq = (
        trending_base
        .group_by(Place.id)
        .having(
            or_(
                func.coalesce(func.count(CheckIn.id), 0) > 0,
                func.coalesce(func.count(Review.id), 0) > 0
            )
        )
        .order_by(text('trending_score DESC'))
        .subquery()
    )

    if q:
        # Build a general place filter for the search keyword within location/other filters
        place_filter = select(Place.id).where(Place.city.ilike(inferred_city))
        if neighborhood:
            place_filter = place_filter.where(
                Place.neighborhood.ilike(f"%{neighborhood}%"))
        if place_type:
            place_filter = place_filter.where(
                Place.categories.ilike(f"%{place_type}%"))
        if min_rating is not None:
            place_filter = place_filter.where(Place.rating >= min_rating)
        if price_tier:
            place_filter = place_filter.where(Place.price_tier == price_tier)
        place_filter = place_filter.where(
            Place.name.ilike(f"%{q}%")).subquery()

        # Main query: all matching places, ordered by trending score if available
        stmt = (
            select(Place)
            .join(place_filter, Place.id == place_filter.c.id)
            .outerjoin(trending_subq, Place.id == trending_subq.c.id)
            .order_by(trending_subq.c.trending_score.desc().nullslast())
            .offset(offset)
            .limit(limit)
        )

        # Count is the number of matching places
        count_stmt = select(func.count()).select_from(place_filter)
    else:
        # Trending-only flow (no general search keyword)
        stmt = (
            select(Place)
            .join(trending_subq, Place.id == trending_subq.c.id)
            .order_by(trending_subq.c.trending_score.desc())
            .offset(offset)
            .limit(limit)
        )

        count_stmt = select(func.count()).select_from(trending_subq)

    # Execute queries
    total = (await db.execute(count_stmt)).scalar_one()
    items = (await db.execute(stmt)).scalars().all()

    # Optional: re-rank by proximity (we have lat/lng)
    from ..utils import haversine_distance

    def distance_or_inf(p: Place) -> float:
        if p.latitude is None or p.longitude is None:
            return float("inf")
        return haversine_distance(lat, lng, p.latitude, p.longitude)
    items = sorted(items, key=distance_or_inf)

    # Fallback to FSQ if no internal trending and enabled
    if total == 0 and app_settings.fsq_trending_enabled and lat is not None and lng is not None:
        fsq = await enhanced_place_data_service.fetch_foursquare_trending(lat=lat, lon=lng, limit=limit)
        now_ts = datetime.now(timezone.utc)
        items_fsq = [
            PlaceResponse(
                id=-(idx + 1),
                name=p.get("name"),
                address=None,
                city=None,
                neighborhood=None,
                latitude=p.get("latitude"),
                longitude=p.get("longitude"),
                categories=p.get("categories"),
                rating=p.get("rating"),
                created_at=now_ts,
            )
            for idx, p in enumerate(fsq)
        ]
        return PaginatedPlaces(items=items_fsq, total=len(items_fsq), limit=limit, offset=offset)

    return PaginatedPlaces(items=items, total=total, limit=limit, offset=offset)


@router.get("/trending/global", response_model=PaginatedPlaces)
async def get_global_trending_places(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    q: str | None = Query(None),
    place_type: str | None = Query(None),
    country: str | None = Query(None),
    city: str | None = Query(None),
    neighborhood: str | None = Query(None),
    min_rating: float | None = Query(None, ge=0, le=5),
    price_tier: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get globally trending places (no auth required)"""
    from ..config import settings as app_settings
    # FSQ override: always use Foursquare-based trending if enabled
    if app_settings.fsq_trending_override:
        if lat is None or lng is None:
            raise HTTPException(
                status_code=400, detail="Provide lat,lng for FSQ trending override")
        fsq = await enhanced_place_data_service.fetch_foursquare_trending(lat=lat, lon=lng, limit=limit)
        now_ts = datetime.now(timezone.utc)
        items = [
            PlaceResponse(
                id=-(idx + 1),
                name=p.get("name"),
                address=None,
                city=None,
                neighborhood=None,
                latitude=p.get("latitude"),
                longitude=p.get("longitude"),
                categories=p.get("categories"),
                rating=p.get("rating"),
                created_at=now_ts,
            )
            for idx, p in enumerate(fsq)
        ]
        if q:
            items = [it for it in items if it.name and q.lower()
                     in it.name.lower()]
        if place_type:
            items = [it for it in items if it.categories and place_type.lower() in str(
                it.categories).lower()]
        if min_rating is not None:
            items = [it for it in items if (it.rating or 0) >= min_rating]
        return PaginatedPlaces(items=items, total=len(items), limit=limit, offset=offset)

    # Use last 7 days for global trending
    window_start = datetime.now(timezone.utc) - timedelta(days=7)

    # Build trending score query
    trending_base = (
        select(
            Place.id,
            Place.name,
            Place.address,
            Place.city,
            Place.neighborhood,
            Place.latitude,
            Place.longitude,
            Place.categories,
            Place.rating,
            Place.created_at,
            # Check-ins count
            func.coalesce(func.count(CheckIn.id), 0).label('checkins_count'),
            # Reviews count
            func.coalesce(func.count(Review.id), 0).label('reviews_count'),
            # Photos count (from reviews)
            func.coalesce(func.count(Photo.id), 0).label('photos_count'),
            # Unique users who checked in
            func.coalesce(func.count(func.distinct(CheckIn.user_id)), 0).label(
                'unique_users'),
            # Calculate trending score
            (
                func.coalesce(func.count(CheckIn.id), 0) * 3 +
                func.coalesce(func.count(Review.id), 0) * 2 +
                func.coalesce(func.count(Photo.id), 0) * 1 +
                func.coalesce(func.count(
                    func.distinct(CheckIn.user_id)), 0) * 2
            ).label('trending_score')
        )
        .outerjoin(CheckIn, and_(
            Place.id == CheckIn.place_id,
            CheckIn.created_at >= window_start
        ))
        .outerjoin(Review, and_(
            Place.id == Review.place_id,
            Review.created_at >= window_start
        ))
        .outerjoin(Photo, and_(
            Review.id == Photo.review_id,
            Photo.created_at >= window_start
        ))
    )

    # No city filter for global trending

    trending_subq = (
        trending_base
        .group_by(Place.id)
        .having(
            or_(
                func.coalesce(func.count(CheckIn.id), 0) > 0,
                func.coalesce(func.count(Review.id), 0) > 0
            )
        )
        .order_by(text('trending_score DESC'))
        .subquery()
    )

    # Main query with pagination
    stmt = (
        select(Place)
        .join(trending_subq, Place.id == trending_subq.c.id)
        .order_by(trending_subq.c.trending_score.desc())
        .offset(offset)
        .limit(limit)
    )

    # Count query for pagination
    count_stmt = (
        select(func.count())
        .select_from(trending_subq)
    )

    # Execute queries
    total = (await db.execute(count_stmt)).scalar_one()
    items = (await db.execute(stmt)).scalars().all()

    # Optional: re-rank by proximity if coordinates provided
    if lat is not None and lng is not None:
        from ..utils import haversine_distance

        def distance_or_inf(p: Place) -> float:
            if p.latitude is None or p.longitude is None:
                return float("inf")
            return haversine_distance(lat, lng, p.latitude, p.longitude)
        items = sorted(items, key=distance_or_inf)

    return PaginatedPlaces(items=items, total=total, limit=limit, offset=offset)


@router.get("/nearby", response_model=PaginatedPlaces)
async def nearby_places(
    lat: float,
    lng: float,
    radius_m: int = 1000,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    from ..config import settings as app_settings
    import logging
    logging.info(f"Nearby places request: lat={lat}, lng={lng}, radius={radius_m}, limit={limit}, offset={offset}")
    paginated: PaginatedPlaces | None = None

    if app_settings.use_postgis:
        try:
            # Use spherical distance in meters without geography casts to avoid SQLAlchemy cache issues
            user_point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
            place_point = func.ST_SetSRID(func.ST_MakePoint(
                Place.longitude, Place.latitude), 4326)
            distance_m = func.ST_DistanceSphere(place_point, user_point)

            # Count within radius (meters)
            total_q = select(func.count(Place.id)).where(
                Place.latitude.is_not(None),
                Place.longitude.is_not(None),
                distance_m <= radius_m,
            )
            total = (await db.execute(total_q)).scalar_one()

            # Fetch places ordered by distance (meters)
            stmt = (
                select(Place)
                .where(
                    Place.latitude.is_not(None),
                    Place.longitude.is_not(None),
                    distance_m <= radius_m,
                )
                .order_by(distance_m.asc())
                .offset(offset)
                .limit(limit)
            )
            items = (await db.execute(stmt)).scalars().all()
            paginated = PaginatedPlaces(
                items=items,
                total=total,
                limit=limit,
                offset=offset,
                external_results=[],
                external_count=0,
            )
        except Exception as e:
            logging.warning(
                f"PostGIS nearby failed, falling back to haversine: {e}")

    if paginated is None:
        logging.info("Using Python fallback for nearby places")
        paginated = await _nearby_places_python_fallback(
            db, lat, lng, radius_m, limit, offset
        )
        logging.info(f"Python fallback returned {paginated.total} places")

    should_fetch_external = False  # Temporarily disable external search to debug
    if not should_fetch_external:
        return paginated

    max_external = max(0, limit - len(paginated.items))
    live_results = await enhanced_place_data_service.search_live_overpass(
        lat=lat,
        lon=lng,
        radius=radius_m,
        query=None,
        types=None,
        limit=max_external,
    )

    normalized_results: list[dict] = []
    for item in live_results[:max_external]:
        record = dict(item)
        record.setdefault("data_source", "osm_overpass")
        lat_val = record.get("latitude")
        lon_val = record.get("longitude")
        if lat_val is None or lon_val is None:
            continue
        if "distance_m" not in record:
            record["distance_m"] = round(
                haversine_distance(lat, lng, lat_val, lon_val) * 1000, 2
            )
        else:
            record["distance_m"] = float(record["distance_m"])
        normalized_results.append(record)

    if not normalized_results:
        return paginated.model_copy(
            update={
                "external_results": [],
                "external_count": 0,
                "external_snapshot_id": None,
                "external_source": None,
                "external_search_key": None,
                "external_fetched_at": None,
            }
        )

    response_results = [ExternalPlaceResult(**record)
                        for record in normalized_results]

    search_key = _build_external_search_key(lat, lng, radius_m, None, None)
    snapshot_id: int | None = None
    fetched_at = datetime.now(timezone.utc)

    snapshot = ExternalSearchSnapshot(
        search_key=search_key,
        latitude=lat,
        longitude=lng,
        radius_m=radius_m,
        query=None,
        types=None,
        source="osm_overpass",
        result_count=len(normalized_results),
        results=normalized_results,
    )

    try:
        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)
        snapshot_id = snapshot.id
        fetched_at = snapshot.fetched_at
    except Exception as exc:  # pragma: no cover - defensive logging only
        await db.rollback()
        logger.warning("Failed to persist nearby external snapshot: %s", exc)

    return paginated.model_copy(
        update={
            "external_results": response_results,
            "external_count": len(response_results),
            "external_snapshot_id": snapshot_id,
            "external_source": "osm_overpass",
            "external_search_key": search_key,
            "external_fetched_at": fetched_at,
        }
    )


@router.get("/{place_id}", response_model=EnhancedPlaceResponse)
async def get_place_details(
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    lat: float | None = Query(
        None, description="User latitude for check-in feasibility"),
    lng: float | None = Query(
        None, description="User longitude for check-in feasibility"),
):
    """
    Get detailed information about a place.

    **Authentication Required:** Yes

    **Enhanced Response Includes:**
    - Basic place information (name, address, coordinates)
    - Real-time statistics (check-ins, reviews, photos)
    - Current activity (who's here now)
    - User-specific data (is checked in, is saved)
    - Recent reviews and photos

    **Statistics:**
    - Average rating and total reviews
    - Active check-ins (last 24 hours)
    - Total check-ins ever
    - Recent reviews (last 30 days)
    - Photos count

    **User Context:**
    - Whether user is currently checked in
    - Whether place is saved to user's lists
    - User's relationship to the place

    **Use Cases:**
    - Place detail pages
    - Pre-check-in information
    - Social proof and activity
    - Place discovery and exploration
    """
    # Get place
    res = await db.execute(select(Place).where(Place.id == place_id))
    place = res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Calculate statistics
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    thirty_days_ago = now - timedelta(days=30)

    # Current active check-ins (last 24h)
    current_checkins_res = await db.execute(
        select(func.count(CheckIn.id))
        .where(CheckIn.place_id == place_id, CheckIn.created_at >= yesterday)
    )
    current_checkins = current_checkins_res.scalar_one()

    # Total check-ins ever
    total_checkins_res = await db.execute(
        select(func.count(CheckIn.id))
        .where(CheckIn.place_id == place_id)
    )
    total_checkins = total_checkins_res.scalar_one()

    # Recent reviews (last 30 days)
    recent_reviews_res = await db.execute(
        select(func.count(Review.id))
        .where(Review.place_id == place_id, Review.created_at >= thirty_days_ago)
    )
    recent_reviews = recent_reviews_res.scalar_one()

    # Photos count
    photos_count_res = await db.execute(
        select(func.count(Photo.id))
        .where(Photo.place_id == place_id)
    )
    photos_count = photos_count_res.scalar_one()

    # Average rating and total reviews
    reviews_stats_res = await db.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.place_id == place_id)
    )
    avg_rating, reviews_count = reviews_stats_res.first()

    # Check if user is currently checked in (last 24h)
    user_checkin_res = await db.execute(
        select(CheckIn.id)
        .where(
            CheckIn.place_id == place_id,
            CheckIn.user_id == current_user.id,
            CheckIn.created_at >= yesterday
        )
    )
    is_checked_in = user_checkin_res.scalar_one_or_none() is not None

    # Check if user has saved this place
    saved_res = await db.execute(
        select(SavedPlace.id)
        .where(SavedPlace.place_id == place_id, SavedPlace.user_id == current_user.id)
    )
    is_saved = saved_res.scalar_one_or_none() is not None

    # Create stats object
    stats = PlaceStats(
        place_id=place_id,
        average_rating=float(avg_rating) if avg_rating else None,
        reviews_count=reviews_count,
        active_checkins=current_checkins
    )

    # Determine if user can check in now
    can_check_in: bool | None = None
    block_reason: str | None = None
    try:
        five_min_ago = now - timedelta(minutes=5)
        same_place_recent = await db.execute(
            select(CheckIn.id).where(
                CheckIn.user_id == current_user.id,
                CheckIn.place_id == place_id,
                CheckIn.created_at >= five_min_ago,
            )
        )
        if same_place_recent.scalar_one_or_none() is not None:
            can_check_in = False
            block_reason = "cooldown"
        else:
            from ..config import settings as app_settings
            if getattr(app_settings, "checkin_enforce_proximity", True):
                if place.latitude is None or place.longitude is None:
                    can_check_in = False
                    block_reason = "place_no_coords"
                elif lat is None or lng is None:
                    can_check_in = False
                    block_reason = "missing_location"
                else:
                    dist_km = haversine_distance(
                        lat, lng, place.latitude, place.longitude)
                    can_check_in = dist_km * \
                        1000 <= getattr(
                            app_settings, "checkin_max_distance_meters", 500)
                    if not can_check_in:
                        block_reason = "too_far"
            else:
                can_check_in = True
    except Exception:
        can_check_in = None
        block_reason = None

    # Create enhanced response
    return EnhancedPlaceResponse(
        id=place.id,
        name=place.name,
        address=place.address,
        country=getattr(place, "country", None),
        city=place.city,
        neighborhood=place.neighborhood,
        latitude=place.latitude,
        longitude=place.longitude,
        categories=place.categories,
        rating=place.rating,
        description=getattr(place, "description", None),
        price_tier=getattr(place, "price_tier", None),
        opening_hours=(place.place_metadata or {}).get(
            "opening_hours") if getattr(place, "place_metadata", None) else None,
        google_maps_url=(f"https://www.google.com/maps/search/?api=1&query={place.latitude},{place.longitude}") if (
            place.latitude and place.longitude) else None,
        created_at=place.created_at,
        stats=stats,
        current_checkins=current_checkins,
        total_checkins=total_checkins,
        recent_reviews=recent_reviews,
        photos_count=photos_count,
        is_checked_in=is_checked_in,
        is_saved=is_saved,
        can_check_in=can_check_in,
        check_in_block_reason=block_reason,
        amenities=(place.place_metadata or {}).get("amenities") if getattr(
            place, "place_metadata", None) else None,
    )


@router.get("/{place_id}/stats", response_model=PlaceStats)
async def get_place_stats(place_id: int, db: AsyncSession = Depends(get_db)):
    """Get place statistics"""
    # Verify place exists
    res = await db.execute(select(Place).where(Place.id == place_id))
    place = res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Calculate statistics
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # Current active check-ins (last 24h)
    current_checkins_res = await db.execute(
        select(func.count(CheckIn.id))
        .where(CheckIn.place_id == place_id, CheckIn.created_at >= yesterday)
    )
    current_checkins = current_checkins_res.scalar_one()

    # Average rating and total reviews
    reviews_stats_res = await db.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.place_id == place_id)
    )
    avg_rating, reviews_count = reviews_stats_res.first()

    return PlaceStats(
        place_id=place_id,
        average_rating=float(avg_rating) if avg_rating else None,
        reviews_count=reviews_count,
        active_checkins=current_checkins
    )


@router.get("/{place_id}/stats/enhanced", response_model=EnhancedPlaceStats, include_in_schema=False)
async def get_enhanced_place_stats(
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get enhanced place statistics with time-based analytics"""

    # Get place
    result = await db.execute(select(Place).where(Place.id == place_id))
    place = result.scalar_one_or_none()

    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    now = datetime.now(timezone.utc)

    # Basic stats
    total_checkins = await db.scalar(
        select(func.count(CheckIn.id)).where(CheckIn.place_id == place_id)
    )
    total_reviews = await db.scalar(
        select(func.count(Review.id)).where(Review.place_id == place_id)
    )
    total_photos = await db.scalar(
        select(func.count(Photo.id)).join(Review, Photo.review_id ==
                                          Review.id).where(Review.place_id == place_id)
    )
    unique_visitors = await db.scalar(
        select(func.count(func.distinct(CheckIn.user_id))).where(
            CheckIn.place_id == place_id)
    )
    average_rating = await db.scalar(
        select(func.avg(Review.rating)).where(Review.place_id == place_id)
    )

    # Popular hours (last 30 days)
    thirty_days_ago = now - timedelta(days=30)
    hourly_stats = await db.execute(
        select(
            func.extract('hour', CheckIn.created_at).label('hour'),
            func.count(CheckIn.id).label('checkins_count'),
            func.count(func.distinct(CheckIn.user_id)).label('unique_users')
        )
        .where(
            CheckIn.place_id == place_id,
            CheckIn.created_at >= thirty_days_ago
        )
        .group_by(text('hour'))
        .order_by(text('checkins_count DESC'))
        .limit(6)
    )

    popular_hours = [
        PlaceHourlyStats(
            hour=int(row.hour),
            checkins_count=row.checkins_count,
            unique_users=row.unique_users
        )
        for row in hourly_stats.fetchall()
    ]

    # Crowd level (current vs average)
    current_checkins = await db.scalar(
        select(func.count(CheckIn.id))
        .where(
            CheckIn.place_id == place_id,
            CheckIn.created_at >= now - timedelta(hours=1)
        )
    )

    # Average check-ins per hour (last 7 days)
    seven_days_ago = now - timedelta(days=7)
    total_recent_checkins = await db.scalar(
        select(func.count(CheckIn.id))
        .where(
            CheckIn.place_id == place_id,
            CheckIn.created_at >= seven_days_ago
        )
    )
    average_checkins_per_hour = total_recent_checkins / \
        (7 * 24) if total_recent_checkins > 0 else 0

    # Determine crowd level
    if current_checkins == 0:
        crowd_level = "low"
    elif current_checkins <= average_checkins_per_hour * 0.5:
        crowd_level = "low"
    elif current_checkins <= average_checkins_per_hour * 1.5:
        crowd_level = "medium"
    elif current_checkins <= average_checkins_per_hour * 2.5:
        crowd_level = "high"
    else:
        crowd_level = "very_high"

    crowd_level_data = PlaceCrowdLevel(
        current_checkins=current_checkins or 0,
        average_checkins=round(average_checkins_per_hour, 2),
        crowd_level=crowd_level
    )

    # Recent activity
    activity_24h = await db.scalar(
        select(func.count(CheckIn.id))
        .where(
            CheckIn.place_id == place_id,
            CheckIn.created_at >= now - timedelta(days=1)
        )
    )
    activity_7d = await db.scalar(
        select(func.count(CheckIn.id))
        .where(
            CheckIn.place_id == place_id,
            CheckIn.created_at >= now - timedelta(days=7)
        )
    )
    activity_30d = await db.scalar(
        select(func.count(CheckIn.id))
        .where(
            CheckIn.place_id == place_id,
            CheckIn.created_at >= now - timedelta(days=30)
        )
    )

    recent_activity = {
        "24h": activity_24h or 0,
        "7d": activity_7d or 0,
        "30d": activity_30d or 0
    }

    return EnhancedPlaceStats(
        total_checkins=total_checkins or 0,
        total_reviews=total_reviews or 0,
        total_photos=total_photos or 0,
        unique_visitors=unique_visitors or 0,
        average_rating=float(average_rating) if average_rating else 0.0,
        popular_hours=popular_hours,
        crowd_level=crowd_level_data,
        recent_activity=recent_activity
    )


@router.get("/{place_id}/whos-here", response_model=PaginatedWhosHere)
async def whos_here(
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Get who's currently checked in at this place.

    **Authentication Required:** Yes

    **Features:**
    - Shows users checked in within last 24 hours
    - Respects privacy settings (visibility controls)
    - Rich user information (name, avatar, check-in time)
    - Photo URLs from check-ins

    **Privacy Enforcement:**
    - Only shows check-ins user has permission to see
    - Respects `public`, `friends` (followers-only), `private` visibility
    - Followers can see followers-only (`friends`) check-ins

    **Response Data:**
    - User ID, name, and avatar
    - Check-in timestamp
    - Photo URLs from the check-in
    - Pagination information

    **Use Cases:**
    - Social discovery at places
    - Real-time activity monitoring
    - Privacy-respecting social features
    - Location-based social networking
    """
    # Verify place exists
    res = await db.execute(select(Place).where(Place.id == place_id))
    place = res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Get check-ins from last 24h
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    # Count total
    total_res = await db.execute(
        select(func.count(CheckIn.id))
        .where(CheckIn.place_id == place_id, CheckIn.created_at >= yesterday)
    )
    total = total_res.scalar_one()

    # Get check-ins with user info
    stmt = (
        select(CheckIn, User.name, User.avatar_url, User.username)
        .join(User, User.id == CheckIn.user_id)
        .where(CheckIn.place_id == place_id, CheckIn.created_at >= yesterday)
        .order_by(CheckIn.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()

    # Filter based on visibility
    from ..utils import can_view_checkin
    items: list[WhosHereItem] = []
    for checkin, user_name, avatar_url, username in rows:
        if await can_view_checkin(db, checkin.user_id, current_user.id, checkin.visibility):
            # photos
            res_ph = await db.execute(select(CheckInPhoto).where(CheckInPhoto.check_in_id == checkin.id).order_by(CheckInPhoto.created_at.asc()))
            urls = [p.url for p in res_ph.scalars().all()]
            items.append(
                WhosHereItem(
                    check_in_id=checkin.id,
                    user_id=checkin.user_id,
                    user_name=user_name or f"User {checkin.user_id}",
                    username=username,
                    user_avatar_url=_convert_single_to_signed_url(avatar_url),
                    created_at=checkin.created_at,
                    photo_urls=urls,
                )
            )

    return PaginatedWhosHere(items=items, total=len(items), limit=limit, offset=offset)


@router.get("/{place_id}/whos-here-count", response_model=dict)
async def whos_here_count(
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get count of people currently checked in at this place (last 24h)"""
    # Verify place exists
    res = await db.execute(select(Place).where(Place.id == place_id))
    place = res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Get check-ins from last 24h
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    # Count total
    total_res = await db.execute(
        select(func.count(CheckIn.id))
        .where(CheckIn.place_id == place_id, CheckIn.created_at >= yesterday)
    )
    total = total_res.scalar_one()

    return {"count": total, "place_id": place_id}


@router.post("/check-ins", response_model=CheckInResponse)
async def create_check_in(
    payload: CheckInCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new check-in at a place.

    **Authentication Required:** Yes

    **Features:**
    - Check-in with optional note and visibility
    - Proximity enforcement (500m default)
    - Rate limiting (5-minute cooldown per place)
    - Uses user's default visibility if not specified

    **Proximity Enforcement:**
    - User must be within 500m of place (configurable)
    - Can be disabled with `APP_CHECKIN_ENFORCE_PROXIMITY=false`
    - Requires valid place coordinates

    **Visibility Options:**
    - `public`: Visible to everyone
    - `friends`: Visible to followers only
    - `private`: Visible only to user

    **Rate Limiting:**
    - 5-minute cooldown between check-ins at same place
    - Prevents spam and duplicate check-ins

    **Check-in Lifecycle:**
    - Expires after 24 hours
    - Appears in "who's here" for 24 hours
    - Creates activity feed entry

    **Use Cases:**
    - Share current location
    - Start social interactions
    - Track visited places
    - Privacy-controlled location sharing
    """
    # Rate limit: prevent duplicate check-ins for same user/place within 5 minutes
    five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    recent = await db.execute(
        select(CheckIn).where(
            CheckIn.user_id == current_user.id,
            CheckIn.place_id == payload.place_id,
            CheckIn.created_at >= five_min_ago,
        )
    )
    if recent.scalars().first():
        raise HTTPException(
            status_code=429, detail="Please wait before checking in again to this place")
    # ensure place exists
    res = await db.execute(select(Place).where(Place.id == payload.place_id))
    place = res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Proximity enforcement (default 500m)
    from ..config import settings as app_settings
    if getattr(app_settings, "checkin_enforce_proximity", True):
        if place.latitude is None or place.longitude is None:
            raise HTTPException(
                status_code=400, detail="Place coordinates missing; cannot verify proximity")
        if payload.latitude is None or payload.longitude is None:
            raise HTTPException(
                status_code=400, detail="Missing current location: latitude and longitude are required")
        distance_km = haversine_distance(
            payload.latitude, payload.longitude, place.latitude, place.longitude)
        max_meters = getattr(app_settings, "checkin_max_distance_meters", 500)
        if distance_km * 1000 > max_meters:
            raise HTTPException(
                status_code=400, detail=f"You must be within {max_meters} meters of {place.name} to check in")

    # default visibility from user settings if not provided
    default_vis = getattr(
        current_user, "checkins_default_visibility", "private")
    check_in = CheckIn(
        user_id=current_user.id,
        place_id=payload.place_id,
        note=payload.note,
        visibility=payload.visibility or default_vis,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(check_in)
    await db.commit()
    await db.refresh(check_in)

    # Create activity for the check-in
    try:
        await create_checkin_activity(
            db=db,
            user_id=current_user.id,
            checkin_id=check_in.id,
            place_name=place.name,
            note=payload.note
        )
    except Exception as e:
        # Log error but don't fail the check-in creation
        logger.error(
            f"Failed to create activity for check-in {check_in.id}: {e}")

    # compute allowed_to_chat
    from ..config import settings as app_settings
    allowed = (datetime.now(timezone.utc) -
               check_in.created_at) <= timedelta(hours=app_settings.place_chat_window_hours)
    return CheckInResponse(
        id=check_in.id,
        user_id=check_in.user_id,
        place_id=check_in.place_id,
        note=check_in.note,
        visibility=check_in.visibility,
        created_at=check_in.created_at,
        expires_at=check_in.expires_at,
        photo_url=_convert_single_to_signed_url(check_in.photo_url),
        photo_urls=[],
        allowed_to_chat=allowed,
    )


@router.post("/check-ins/full", response_model=CheckInResponse)
async def create_check_in_full(
    place_id: int = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    note: str | None = Form(None),
    visibility: str | None = Form(None),
    files: list[UploadFile] | None = File(None),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a check-in with optional photos in one request.

    **Authentication Required:** Yes

    **Features:**
    - One-shot check-in creation with multiple photos
    - Proximity enforcement (500m default)
    - Rate limiting (5-minute cooldown per place)

    **Proximity Enforcement:**
    - User must be within 500m of place (configurable)
    - Can be disabled with `APP_CHECKIN_ENFORCE_PROXIMITY=false`
    - Requires valid place coordinates

    **Photo Upload:**
    - **Optional**: Photos are completely optional for check-ins
    - Multiple photos supported when provided
    - Formats: JPEG, PNG, WebP
    - Max size: 10MB per photo
    - Stored in S3 with signed URLs for secure access

    **Rate Limiting:**
    - 5-minute cooldown between check-ins at same place
    - Prevents spam and duplicate check-ins

    **Visibility:**
    - Uses user's default if not specified
    - Options: public, friends (followers), private

    **Use Cases:**
    - Quick check-in with photos
    - Social sharing
    - Location-based social updates
    """
    # Rate limit: prevent duplicate check-ins for same user/place within 5 minutes
    five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    recent = await db.execute(
        select(CheckIn).where(
            CheckIn.user_id == current_user.id,
            CheckIn.place_id == place_id,
            CheckIn.created_at >= five_min_ago,
        )
    )
    if recent.scalars().first():
        raise HTTPException(
            status_code=429, detail="Please wait before checking in again to this place")

    # ensure place exists
    res = await db.execute(select(Place).where(Place.id == place_id))
    place = res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Proximity enforcement (default 500m)
    from ..config import settings as app_settings
    if getattr(app_settings, "checkin_enforce_proximity", True):
        if place.latitude is None or place.longitude is None:
            raise HTTPException(
                status_code=400, detail="Place coordinates missing; cannot verify proximity")
        distance_km = haversine_distance(
            latitude, longitude, place.latitude, place.longitude)
        max_meters = getattr(app_settings, "checkin_max_distance_meters", 500)
        if distance_km * 1000 > max_meters:
            raise HTTPException(
                status_code=400, detail=f"You must be within {max_meters} meters of {place.name} to check in")

    # default visibility from user settings if not provided
    default_vis = getattr(
        current_user, "checkins_default_visibility", "private")
    check_in = CheckIn(
        user_id=current_user.id,
        place_id=place_id,
        note=note,
        visibility=visibility or default_vis,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(check_in)
    await db.flush()  # get check_in.id before committing

    # Save photos if provided (streaming to avoid memory issues)
    if files:
        for file in files:
            if not file:
                continue

            # Validate file type and size during streaming
            if not file.content_type or not isinstance(file.content_type, str) or not file.content_type.startswith('image/'):
                raise HTTPException(
                    status_code=400,
                    detail="File must be an image (JPEG, PNG, WebP)"
                )

            # Stream file content in chunks to avoid memory issues
            max_size = 10 * 1024 * 1024  # 10MB per photo
            content = b""
            chunk_size = 64 * 1024  # 64KB chunks
            total_size = 0

            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                content += chunk
                total_size += len(chunk)

                # Check size during streaming
                if total_size > max_size:
                    raise HTTPException(
                        status_code=400,
                        detail="Photo file size must be less than 10MB"
                    )

            try:
                url_path = await StorageService.save_checkin_photo(check_in.id, file.filename or "upload.jpg", content)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            db.add(CheckInPhoto(check_in_id=check_in.id, url=url_path))
            # keep backward-compatible single photo_url set to last uploaded
            check_in.photo_url = url_path

    # Note: Collection assignment removed - using saved places collections instead

    await db.commit()
    await db.refresh(check_in)

    # enrich response with photo_urls
    res_ph = await db.execute(
        select(CheckInPhoto).where(CheckInPhoto.check_in_id ==
                                   check_in.id).order_by(CheckInPhoto.created_at.asc())
    )
    photo_urls = [p.url for p in res_ph.scalars().all()]
    # Convert S3 keys to signed URLs
    photo_urls = _convert_to_signed_urls(photo_urls)

    # Create activity for the check-in
    try:
        await create_checkin_activity(
            db=db,
            user_id=current_user.id,
            checkin_id=check_in.id,
            place_name=place.name,
            note=note,
        )
    except Exception as e:
        logger.error(
            f"Failed to create activity for check-in {check_in.id}: {e}")

    return CheckInResponse(
        id=check_in.id,
        user_id=check_in.user_id,
        place_id=check_in.place_id,
        note=check_in.note,
        visibility=check_in.visibility,
        created_at=check_in.created_at,
        expires_at=check_in.expires_at,
        photo_url=_convert_single_to_signed_url(check_in.photo_url),
        photo_urls=photo_urls,
    )


@router.post("/check-ins/{check_in_id}/photo", response_model=CheckInResponse)
async def upload_checkin_photo(
    check_in_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # fetch check-in and authz
    res = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    checkin = res.scalars().first()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")
    if checkin.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    # save file via storage service
    import os
    from uuid import uuid4
    _, ext = os.path.splitext(file.filename or "")
    if not ext:
        ext = ".jpg"
    filename = f"{uuid4().hex}{ext}"
    content = await file.read()
    try:
        url_path = await StorageService.save_checkin_photo(check_in_id, filename, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    cip = CheckInPhoto(check_in_id=check_in_id, url=url_path)
    db.add(cip)
    # keep backward-compatible single photo_url set to last uploaded
    checkin.photo_url = url_path
    await db.commit()
    await db.refresh(checkin)
    # enrich response with photo_urls
    res_ph = await db.execute(select(CheckInPhoto).where(CheckInPhoto.check_in_id == check_in_id).order_by(CheckInPhoto.created_at.asc()))
    photo_urls = [p.url for p in res_ph.scalars().all()]
    # Convert S3 keys to signed URLs
    photo_urls = _convert_to_signed_urls(photo_urls)

    from ..config import settings as app_settings
    allowed = (datetime.now(timezone.utc) -
               checkin.created_at) <= timedelta(hours=app_settings.place_chat_window_hours)
    return CheckInResponse(
        id=checkin.id,
        user_id=checkin.user_id,
        place_id=checkin.place_id,
        note=checkin.note,
        visibility=checkin.visibility,
        created_at=checkin.created_at,
        expires_at=checkin.expires_at,
        photo_url=_convert_single_to_signed_url(checkin.photo_url),
        photo_urls=photo_urls,
        allowed_to_chat=allowed,
    )


@router.delete("/check-ins/{check_in_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checkin_photo(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    checkin = res.scalars().first()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")
    if checkin.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    # delete all associated photos records and underlying files (best-effort)
    res_ph = await db.execute(select(CheckInPhoto).where(CheckInPhoto.check_in_id == check_in_id))
    for ph in res_ph.scalars().all():
        try:
            import os
            filename = os.path.basename(ph.url)
            await StorageService.delete_checkin_photo(check_in_id, filename)
        except Exception:
            pass
        await db.delete(ph)
    checkin.photo_url = None
    await db.commit()
    return None


@router.get("/check-ins/{check_in_id}/photos", response_model=list[CheckInPhotoResponse])
async def list_checkin_photos(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Only owner can list for now
    res = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    checkin = res.scalars().first()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")
    if checkin.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    res_ph = await db.execute(
        select(CheckInPhoto).where(CheckInPhoto.check_in_id ==
                                   check_in_id).order_by(CheckInPhoto.created_at.asc())
    )
    photos = res_ph.scalars().all()
    return [CheckInPhotoResponse(id=p.id, check_in_id=p.check_in_id, url=_convert_single_to_signed_url(p.url), created_at=p.created_at) for p in photos]


@router.delete("/check-ins/{check_in_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checkin_photo_item(
    check_in_id: int,
    photo_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    checkin = res.scalars().first()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")
    if checkin.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    res_ph = await db.execute(
        select(CheckInPhoto).where(CheckInPhoto.id == photo_id,
                                   CheckInPhoto.check_in_id == check_in_id)
    )
    photo = res_ph.scalars().first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    # best-effort file delete
    try:
        import os
        filename = os.path.basename(photo.url)
        await StorageService.delete_checkin_photo(check_in_id, filename)
    except Exception:
        pass
    await db.delete(photo)
    await db.commit()
    return None


@router.delete("/check-ins/{check_in_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_check_in(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = res.scalars().first()
    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")
    if check_in.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not allowed to delete this check-in")
    await db.delete(check_in)
    await db.commit()
    return None


@router.get("/{place_id}/whos-here", response_model=list[CheckInResponse])
async def whos_here(
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    now = datetime.now(timezone.utc)

    # Get all active check-ins for this place
    res = await db.execute(
        select(CheckIn)
        .where(
            CheckIn.place_id == place_id,
            CheckIn.expires_at >= now,
        )
        .order_by(CheckIn.created_at.desc())
        .offset(offset)
        .limit(limit * 2)  # Get more to filter by visibility
    )
    all_checkins = res.scalars().all()

    # Filter check-ins based on visibility rules
    visible_checkins = []
    for checkin in all_checkins:
        if await can_view_checkin(db, checkin.user_id, current_user.id, checkin.visibility):
            visible_checkins.append(checkin)
            if len(visible_checkins) >= limit:
                break

    # hydrate photo_urls
    result: list[CheckInResponse] = []
    for ci in visible_checkins:
        res_ph = await db.execute(
            select(CheckInPhoto)
            .where(CheckInPhoto.check_in_id == ci.id)
            .order_by(CheckInPhoto.created_at.asc())
        )
        urls = [p.url for p in res_ph.scalars().all()]
        # Convert S3 keys to signed URLs
        urls = _convert_to_signed_urls(urls)

        from ..config import settings as app_settings
        allowed = (datetime.now(timezone.utc) -
                   ci.created_at) <= timedelta(hours=app_settings.place_chat_window_hours)
        result.append(
            CheckInResponse(
                id=ci.id,
                user_id=ci.user_id,
                place_id=ci.place_id,
                note=ci.note,
                visibility=ci.visibility,
                created_at=ci.created_at,
                expires_at=ci.expires_at,
                photo_url=_convert_single_to_signed_url(ci.photo_url),
                photo_urls=urls,
                allowed_to_chat=allowed,
            )
        )
    return result


@router.get("/{place_id}/whos-here/count")
async def whos_here_count(
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    now = datetime.now(timezone.utc)

    # Get all active check-ins for this place
    res = await db.execute(
        select(CheckIn).where(
            CheckIn.place_id == place_id,
            CheckIn.expires_at >= now,
        )
    )
    all_checkins = res.scalars().all()

    # Count check-ins based on visibility rules
    count = 0
    for checkin in all_checkins:
        if await can_view_checkin(db, checkin.user_id, current_user.id, checkin.visibility):
            count += 1

    return {"count": count}


@router.get("/me/check-ins", response_model=PaginatedCheckIns)
async def my_check_ins(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    total = (
        await db.execute(select(func.count(CheckIn.id)).where(CheckIn.user_id == current_user.id))
    ).scalar_one()
    res = await db.execute(
        select(CheckIn)
        .where(CheckIn.user_id == current_user.id)
        .order_by(CheckIn.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = res.scalars().all()
    enriched: list[CheckInResponse] = []
    for ci in items:
        res_ph = await db.execute(
            select(CheckInPhoto)
            .where(CheckInPhoto.check_in_id == ci.id)
            .order_by(CheckInPhoto.created_at.asc())
        )
        urls = [p.url for p in res_ph.scalars().all()]
        # Convert S3 keys to signed URLs
        urls = _convert_to_signed_urls(urls)

        from ..config import settings as app_settings
        allowed = (datetime.now(timezone.utc) -
                   ci.created_at) <= timedelta(hours=app_settings.place_chat_window_hours)
        enriched.append(
            CheckInResponse(
                id=ci.id,
                user_id=ci.user_id,
                place_id=ci.place_id,
                note=ci.note,
                visibility=ci.visibility,
                created_at=ci.created_at,
                expires_at=ci.expires_at,
                photo_url=_convert_single_to_signed_url(ci.photo_url),
                photo_urls=urls,
                allowed_to_chat=allowed,
            )
        )
    return PaginatedCheckIns(items=enriched, total=total, limit=limit, offset=offset)


@router.post("/{place_id}/reviews", response_model=ReviewResponse)
async def create_review(
    place_id: int,
    payload: ReviewCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # confirm place exists and load instance
    place_res = await db.execute(select(Place).where(Place.id == place_id))
    place = place_res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Upsert user's review for this place (one review per user per place)
    existing_res = await db.execute(
        select(Review).where(
            Review.user_id == current_user.id,
            Review.place_id == place_id,
        )
    )
    existing = existing_res.scalars().first()

    if existing:
        existing.rating = payload.rating
        existing.text = payload.text
        review = existing
    else:
        review = Review(
            user_id=current_user.id,
            place_id=place_id,
            rating=payload.rating,
            text=payload.text,
        )
        db.add(review)

    await db.commit()
    await db.refresh(review)

    # Recalculate and persist average rating on the place
    avg_res = await db.execute(
        select(func.avg(Review.rating)).where(Review.place_id == place_id)
    )
    avg_rating = avg_res.scalar() or 0
    place.rating = float(avg_rating)
    await db.commit()

    return review


@router.delete("/{place_id}/reviews/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_review(
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ensure review exists
    res = await db.execute(
        select(Review).where(
            Review.user_id == current_user.id,
            Review.place_id == place_id,
        )
    )
    review = res.scalars().first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    await db.delete(review)
    await db.commit()

    # Recalculate place average
    avg_res = await db.execute(
        select(func.avg(Review.rating)).where(Review.place_id == place_id)
    )
    avg_rating = avg_res.scalar()
    place_res = await db.execute(select(Place).where(Place.id == place_id))
    place = place_res.scalar_one_or_none()
    if place is not None:
        place.rating = float(avg_rating) if avg_rating is not None else None
        await db.commit()
    return None


@router.get("/{place_id}/reviews", response_model=PaginatedReviews)
async def list_reviews(
    place_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    total = (
        await db.execute(select(func.count(Review.id)).where(Review.place_id == place_id))
    ).scalar_one()
    res = await db.execute(
        select(Review)
        .where(Review.place_id == place_id)
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = res.scalars().all()
    return PaginatedReviews(items=items, total=total, limit=limit, offset=offset)


@router.post("/saved", response_model=SavedPlaceResponse)
async def save_place(
    payload: SavedPlaceCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ensure place exists
    res = await db.execute(select(Place).where(Place.id == payload.place_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Place not found")

    # Prevent duplicates
    existing = await db.execute(
        select(SavedPlace).where(
            SavedPlace.user_id == current_user.id,
            SavedPlace.place_id == payload.place_id,
        )
    )
    saved = existing.scalars().first()
    if saved:
        # Optionally update list name if provided
        if payload.list_name is not None and payload.list_name != saved.list_name:
            saved.list_name = payload.list_name
            await db.commit()
            await db.refresh(saved)
        return saved

    # Default collection name when not provided
    default_collection = payload.list_name or "Favorites"

    saved_new = SavedPlace(
        user_id=current_user.id,
        place_id=payload.place_id,
        list_name=default_collection,
    )
    db.add(saved_new)
    await db.commit()
    await db.refresh(saved_new)
    return saved_new


@router.get("/saved/me", response_model=PaginatedSavedPlaces)
async def list_saved_places(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    collection: str | None = Query(
        None, description="Optional collection name (list_name) to filter by"),
):
    base = select(SavedPlace).where(SavedPlace.user_id == current_user.id)
    count_base = select(func.count(SavedPlace.id)).where(
        SavedPlace.user_id == current_user.id)
    if collection:
        # Normalize: trim and lowercase; treat NULL/empty as "Favorites"
        norm = collection.strip().lower()
        coalesced = func.coalesce(func.nullif(
            SavedPlace.list_name, ''), literal("Favorites"))
        normalized = func.lower(func.trim(coalesced))
        base = base.where(normalized == norm)
        count_base = count_base.where(normalized == norm)

    total = (await db.execute(count_base)).scalar_one()
    res = await db.execute(base.offset(offset).limit(limit))
    items = res.scalars().all()
    return PaginatedSavedPlaces(items=items, total=total, limit=limit, offset=offset)


@router.get("/saved/collections", response_model=list[str])
async def list_saved_collections(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the list of distinct collection names (list_name) for the current user's saved places."""
    res = await db.execute(
        select(SavedPlace.list_name)
        .where(SavedPlace.user_id == current_user.id)
        .group_by(SavedPlace.list_name)
        .order_by(SavedPlace.list_name.asc())
    )
    names = [row[0] or "Favorites" for row in res.all()]
    # Ensure at least default exists for UX
    return names or ["Favorites"]


@router.get("/saved/collections/{collection_name}", response_model=dict)
async def get_saved_collection(
    collection_name: str,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific saved place collection."""
    # Get collection info
    collection_query = (
        select(
            SavedPlace.list_name,
            func.count(SavedPlace.id).label('count'),
            func.array_agg(SavedPlace.place_id).label('place_ids')
        )
        .where(
            SavedPlace.user_id == current_user.id,
            func.lower(
                func.trim(
                    func.coalesce(func.nullif(
                        SavedPlace.list_name, ''), literal("Favorites"))
                )
            ) == collection_name.strip().lower()
        )
        .group_by(SavedPlace.list_name)
    )

    result = await db.execute(collection_query)
    collection_data = result.first()

    if not collection_data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Collection not found")

    name, count, place_ids = collection_data

    # Get up to 4 random photos from places in this collection
    photos: list[str] = []
    if place_ids and len(place_ids) > 0:
        # Prefer place photos
        photos_result = await db.execute(
            select(Photo.url)
            .where(Photo.place_id.in_(place_ids))
            .order_by(func.random())
            .limit(4)
        )
        photo_urls = photos_result.scalars().all()
        photos = list(photo_urls)
        # Fallback to general check-in photos if no place photos exist
        if not photos:
            ciph_result = await db.execute(
                select(CheckInPhoto.url)
                .join(CheckIn, CheckInPhoto.check_in_id == CheckIn.id)
                .where(CheckIn.place_id.in_(place_ids))
                .order_by(func.random())
                .limit(4)
            )
            photos = list(ciph_result.scalars().all())
        photos = _convert_to_signed_urls(photos)

    return {
        "name": name or "Favorites",
        "count": count,
        "photos": photos
    }


@router.get("/saved/collections/{collection_name}/items", response_model=list[dict])
async def get_saved_collection_items(
    collection_name: str,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get items in a specific saved place collection."""
    # Get all places in this collection for the current user
    places_query = (
        select(
            SavedPlace,
            Place.name,
            Place.address,
            Place.city,
            Place.latitude,
            Place.longitude,
            Place.rating,
            Place.description,
            Place.categories
        )
        .outerjoin(Place, SavedPlace.place_id == Place.id)
        .where(
            SavedPlace.user_id == current_user.id,
            func.lower(
                func.trim(
                    func.coalesce(func.nullif(
                        SavedPlace.list_name, ''), literal("Favorites"))
                )
            ) == collection_name.strip().lower()
        )
        .order_by(SavedPlace.created_at.desc())
    )

    result = await db.execute(places_query)
    items = result.all()

    collection_items = []
    for saved_place, place_name, address, city, latitude, longitude, rating, description, categories in items:
        # Get photos for this place
        photos_query = (
            select(Photo.url)
            .where(Photo.place_id == saved_place.place_id)
            .order_by(Photo.created_at.desc())
            .limit(10)  # Limit to prevent too many photos
        )
        photos_result = await db.execute(photos_query)
        photo_urls = photos_result.scalars().all()
        photos = _convert_to_signed_urls(list(photo_urls))

        collection_items.append({
            "saved_place_id": saved_place.id,
            "place_id": saved_place.place_id,
            "place_name": place_name,
            "address": address,
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "rating": rating,
            "description": description,
            "categories": categories,
            "photos": photos,
            "saved_at": saved_place.created_at
        })

    return collection_items


@router.delete("/saved/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_place(
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(SavedPlace).where(
            SavedPlace.user_id == current_user.id,
            SavedPlace.place_id == place_id,
        )
    )
    saved = res.scalars().first()
    if not saved:
        raise HTTPException(status_code=404, detail="Saved place not found")
    await db.delete(saved)
    await db.commit()
    return None


@router.get("/me/reviews", response_model=PaginatedReviews)
async def my_reviews(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    total = (
        await db.execute(select(func.count(Review.id)).where(Review.user_id == current_user.id))
    ).scalar_one()
    res = await db.execute(
        select(Review)
        .where(Review.user_id == current_user.id)
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = res.scalars().all()
    return PaginatedReviews(items=items, total=total, limit=limit, offset=offset)


# ============================================================================
# PLACE DATA INTEGRATION ENDPOINTS
# ============================================================================

@router.get("/external/test")
async def test_external_endpoint():
    """Test endpoint to verify external routes are working"""
    return {"message": "External endpoints are working!"}


@router.get("/external/search", response_model=ExternalSearchResponse)
async def search_external_places(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius: int = Query(5000, ge=100, le=50000,
                        description="Search radius in meters"),
    query: str = Query(None, description="Optional search query"),
    types: str = Query(
        None, description="Comma-separated place types (e.g., restaurant,cafe)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db)
):
    """
    Search live OpenStreetMap (Overpass) data and keep a history snapshot.

    **Authentication Required:** No (public endpoint)

    **Features:**
    - Live queries against free OSM/Overpass data
    - Optional text and type filtering
    - Results ranked by proximity
    - Every response persisted for historical analysis (no place seeding)

    **Parameters:**
    - `lat`/`lon`: Search center coordinates
    - `radius`: Search radius in meters (100-50000)
    - `query`: Optional case-insensitive name fragment
    - `types`: Optional comma-separated list of desired categories
    - `limit`: Max results returned (1-100)
    """
    try:
        type_list = [t.strip() for t in types.split(
            ",") if t.strip()] if types else None

        live_results = await enhanced_place_data_service.search_live_overpass(
            lat=lat,
            lon=lon,
            radius=radius,
            query=query,
            types=type_list,
            limit=limit,
        )

        normalized_results: list[dict] = []
        for item in live_results[:limit]:
            record = dict(item)
            record.setdefault("data_source", "osm_overpass")
            lat_val = record.get("latitude")
            lon_val = record.get("longitude")
            if lat_val is None or lon_val is None:
                continue
            if "distance_m" not in record:
                record["distance_m"] = round(
                    haversine_distance(lat, lon, lat_val, lon_val) * 1000, 2
                )
            else:
                record["distance_m"] = float(record["distance_m"])
            normalized_results.append(record)

        search_key = _build_external_search_key(
            lat, lon, radius, query, type_list)

        response_results = [ExternalPlaceResult(**record)
                            for record in normalized_results]

        snapshot_id: int | None = None
        fetched_at = datetime.now(timezone.utc)

        snapshot = ExternalSearchSnapshot(
            search_key=search_key,
            latitude=lat,
            longitude=lon,
            radius_m=radius,
            query=query,
            types=",".join(type_list) if type_list else None,
            source="osm_overpass",
            result_count=len(normalized_results),
            results=normalized_results,
        )

        try:
            db.add(snapshot)
            await db.commit()
            await db.refresh(snapshot)
            snapshot_id = snapshot.id
            fetched_at = snapshot.fetched_at
        except Exception as exc:  # pragma: no cover - logging only
            await db.rollback()
            logger.warning(
                "Failed to persist external search snapshot: %s", exc)

        return ExternalSearchResponse(
            source="osm_overpass",
            count=len(response_results),
            fetched_at=fetched_at,
            snapshot_id=snapshot_id,
            search_key=search_key,
            results=response_results,
        )

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive path
        logger.error("Failed to search external places: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search external places",
        ) from e


@router.get("/{place_id}/enrich", response_model=dict)
async def enrich_place_data(
    place_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Enrich place data with information from external sources.

    **Authentication Required:** No (public endpoint)

    **Features:**
    - Fetches additional data from external APIs
    - Updates place with ratings, photos, hours, etc.
    - Supports multiple data sources
    - Caches enriched data in metadata field

    **Data Enrichment:**
    - Ratings and review counts
    - Opening hours
    - Contact information
    - Photos and media
    - Price levels
    - Additional categories

    **Response:**
    - Updated place information
    - Enriched metadata
    - Data source information

    **Use Cases:**
    - Enhance place profiles with external data
    - Keep place information up-to-date
    - Provide richer place details
    """
    try:
        # Get place from database
        place_result = await db.execute(select(Place).where(Place.id == place_id))
        place = place_result.scalar_one_or_none()

        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        # Enrich place data
        enriched_place = await enhanced_place_data_service.enrich_place_data(place)

        # Save enriched data
        await db.commit()
        await db.refresh(enriched_place)

        return {
            "id": enriched_place.id,
            "name": enriched_place.name,
            "rating": enriched_place.rating,
            "categories": enriched_place.categories,
            "website": enriched_place.website,
            "phone": enriched_place.phone,
            "metadata": enriched_place.place_metadata,
            "data_source": enriched_place.data_source,
            "enriched": True
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enrich place data: {str(e)}"
        )


@router.get("/external/suggestions", response_model=list[dict], include_in_schema=False)
async def get_external_place_suggestions(
    query: str = Query(..., min_length=1, description="Search query"),
    lat: float = Query(
        None, description="Optional latitude for location-based suggestions"),
    lon: float = Query(
        None, description="Optional longitude for location-based suggestions"),
    limit: int = Query(10, ge=1, le=20, description="Number of suggestions"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get place suggestions from external data sources.

    **Authentication Required:** No (public endpoint)

    **Features:**
    - Real-time place suggestions
    - Location-aware results (if coordinates provided)
    - Multiple data source integration
    - Fast autocomplete functionality

    **Parameters:**
    - `query`: Search term (minimum 2 characters)
    - `lat`/`lon`: Optional location for better results
    - `limit`: Number of suggestions to return

    **Response:**
    - List of place suggestions
    - Includes basic place information
    - Ready for autocomplete UI

    **Use Cases:**
    - Place search autocomplete
    - Quick place discovery
    - Location-based suggestions
    """
    try:
        if lat is not None and lon is not None:
            # Location-based search
            from ..config import settings as app_settings
            places = await enhanced_place_data_service._search_places_in_db(
                lat=lat,
                lon=lon,
                radius=app_settings.external_suggestions_radius_m,
                query=query,
                limit=limit,
                db=db
            )
        else:
            # General search (OpenStreetMap only for now)
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": "Circles-App/1.0"}
            ) as client:
                url = "https://nominatim.openstreetmap.org/search"
                params = {
                    'q': query,
                    'format': 'json',
                    'limit': limit,
                    'addressdetails': 1
                }
                response = await client.get(url, params=params)
                data = response.json()

                places = [
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

        # Return suggestions (limit results)
        return places[:limit]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get place suggestions: {str(e)}"
        )


# ============================================================================
# ENHANCED PLACE DATA ENDPOINTS (OSM Overpass + Foursquare Enrichment)
# ============================================================================

@router.post("/seed/from-osm", response_model=dict)
async def seed_places_from_osm(
    min_lat: float = Query(..., description="Minimum latitude"),
    min_lon: float = Query(..., description="Minimum longitude"),
    max_lat: float = Query(..., description="Maximum latitude"),
    max_lon: float = Query(..., description="Maximum longitude"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Seed places from OpenStreetMap Overpass API.

    **Authentication Required:** Yes (Admin only)

    **Features:**
    - Fetches places from OSM Overpass API
    - Covers amenities, shops, and leisure facilities
    - Automatic deduplication
    - Batch processing for large areas

    **Parameters:**
    - `min_lat`/`min_lon`: Southwest corner of bounding box
    - `max_lat`/`max_lon`: Northeast corner of bounding box

    **OSM Tags Included:**
    - Amenities: cafe, restaurant, fast_food, bank, atm, pharmacy, hospital, school, university, fuel
    - Shops: supermarket, mall
    - Leisure: park, fitness_centre

    **Response:**
    - Number of places seeded
    - Processing time
    - Success status

    **Use Cases:**
    - Initial data population for new regions
    - Bulk place data import
    - Geographic area coverage
    """
    try:
        start_time = datetime.now(timezone.utc)
        bbox = (min_lat, min_lon, max_lat, max_lon)

        seeded_count = await enhanced_place_data_service.seed_from_osm_overpass(db, bbox)

        processing_time = (datetime.now(timezone.utc) -
                           start_time).total_seconds()

        return {
            "success": True,
            "seeded_count": seeded_count,
            "processing_time_seconds": processing_time,
            "bbox": bbox,
            "message": f"Successfully seeded {seeded_count} places from OSM Overpass"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seed places from OSM: {str(e)}"
        )


@router.get("/search/enhanced", response_model=list[dict], include_in_schema=False)
async def search_places_enhanced(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius: int = Query(5000, ge=100, le=50000,
                        description="Search radius in meters"),
    query: str = Query(None, description="Optional search query"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    enable_enrichment: bool = Query(
        True, description="Enable Foursquare enrichment"),
    db: AsyncSession = Depends(get_db)
):
    """
    Enhanced place search with automatic enrichment.

    **Authentication Required:** No (public endpoint)

    **Features:**
    - Searches pre-seeded places in database
    - Automatic Foursquare enrichment for stale/missing data
    - Quality scoring and intelligent ranking
    - Distance-based filtering and sorting

    **Enrichment Logic:**
    - Only enriches places that need it (missing data or stale)
    - Hot places: 14-day TTL, Cold places: 60-day TTL
    - Name similarity ≥ 0.65 + distance ≤ 150m matching
    - Quality scoring: phone (+0.3), hours (+0.3), photos (+0.2), recent (+0.2)

    **Ranking Algorithm:**
    - 45% distance score
    - 25% text match score
    - 15% category boost
    - 15% quality score

    **Parameters:**
    - `lat`/`lon`: Search center coordinates
    - `radius`: Search radius in meters (100-50000)
    - `query`: Optional search term
    - `limit`: Maximum results (1-100)
    - `enable_enrichment`: Enable/disable Foursquare enrichment

    **Response:**
    - List of places with quality scores
    - Enrichment status for each place
    - Distance and ranking information

    **Use Cases:**
    - Primary place discovery
    - Location-based search
    - High-quality place recommendations
    """
    try:
        if enable_enrichment:
            # Use enhanced search with enrichment
            places = await enhanced_place_data_service.search_places_with_enrichment(
                lat=lat,
                lon=lon,
                radius=radius,
                query=query,
                limit=limit,
                db=db
            )
        else:
            # Use basic search without enrichment
            places = await enhanced_place_data_service._search_places_in_db(
                lat=lat,
                lon=lon,
                radius=radius,
                query=query,
                limit=limit,
                db=db
            )
            # Convert to response format
            places = [
                {
                    **enhanced_place_data_service._place_to_dict(place),
                    'quality_score': enhanced_place_data_service._calculate_quality_score(place)
                }
                for place in places
            ]

        return places

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search places: {str(e)}"
        )


@router.post("/enrich/{place_id}", response_model=dict)
async def enrich_place_manually(
    place_id: int,
    force: bool = Query(
        False, description="Force enrichment even if not needed"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually enrich a specific place with Foursquare data.

    **Authentication Required:** Yes (Admin only)

    **Features:**
    - Enriches place with Foursquare venue data
    - Updates phone, website, hours, photos, rating
    - Intelligent venue matching
    - Quality score recalculation

    **Enrichment Process:**
    1. Search for matching Foursquare venues
    2. Find best match (name similarity + distance)
    3. Fetch detailed venue information
    4. Update place with enriched data
    5. Store enrichment metadata

    **Parameters:**
    - `place_id`: ID of place to enrich
    - `force`: Force enrichment even if not needed

    **Response:**
    - Enrichment status
    - Updated place data
    - Quality score
    - Match information

    **Use Cases:**
    - Manual data quality improvement
    - Testing enrichment functionality
    - Force refresh of stale data
    """
    try:
        # Get place from database
        place_result = await db.execute(select(Place).where(Place.id == place_id))
        place = place_result.scalar_one_or_none()

        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        # Check if enrichment is needed (unless forced)
        if not force and not enhanced_place_data_service._needs_enrichment(place):
            return {
                "enriched": False,
                "message": "Place does not need enrichment",
                "quality_score": enhanced_place_data_service._calculate_quality_score(place),
                "last_enriched_at": place.last_enriched_at.isoformat() if place.last_enriched_at else None
            }

        # Perform enrichment
        enriched = await enhanced_place_data_service.enrich_place_if_needed(place, db)

        if enriched:
            await db.refresh(place)
            return {
                "enriched": True,
                "message": "Place successfully enriched",
                "quality_score": enhanced_place_data_service._calculate_quality_score(place),
                "last_enriched_at": place.last_enriched_at.isoformat() if place.last_enriched_at else None,
                "place_data": enhanced_place_data_service._place_to_dict(place)
            }
        else:
            return {
                "enriched": False,
                "message": "No matching Foursquare venue found",
                "quality_score": enhanced_place_data_service._calculate_quality_score(place),
                "last_enriched_at": place.last_enriched_at.isoformat() if place.last_enriched_at else None
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enrich place: {str(e)}"
        )


@router.get("/stats/enrichment", response_model=dict)
async def get_enrichment_stats(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get enrichment statistics and data quality metrics.

    **Authentication Required:** Yes (Admin only)

    **Features:**
    - Overall enrichment statistics
    - Data quality metrics
    - Source distribution
    - TTL compliance

    **Metrics:**
    - Total places count
    - Enriched places count
    - Average quality score
    - Data source distribution
    - TTL compliance rate

    **Response:**
    - Statistical overview
    - Quality metrics
    - Source breakdown
    - Recommendations

    **Use Cases:**
    - System monitoring
    - Data quality assessment
    - Performance optimization
    """
    try:
        from ..services.place_metrics_service import place_metrics_service
        return await place_metrics_service.get_enrichment_stats(db)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get enrichment stats: {str(e)}"
        )


@router.get("/stats/seeding", response_model=dict)
async def get_seeding_status(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get seeding status and statistics.

    **Authentication Required:** Yes (Admin only)

    **Features:**
    - Check if data has been seeded
    - View seeding statistics
    - Monitor data distribution

    **Response:**
    - Seeding status
    - Total places count
    - Source distribution
    - Saudi cities coverage

    **Use Cases:**
    - System monitoring
    - Data completeness check
    - Deployment verification
    """
    try:
        from ..services.auto_seeder_service import auto_seeder_service
        return await auto_seeder_service.get_seeding_status(db)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get seeding status: {str(e)}"
        )


@router.post("/promote/foursquare", response_model=dict)
async def promote_foursquare_place(
    fsq_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Promote a Foursquare-only place to the database.

    **Authentication Required:** Yes (Admin only)

    **Features:**
    - Creates a new place record from Foursquare data
    - Enriches the place with full details and photos
    - Prevents duplicates by checking existing places

    **Parameters:**
    - fsq_id: Foursquare venue ID to promote

    **Response:**
    - Created place details
    - Enrichment status
    - Quality metrics

    **Use Cases:**
    - Promoting discovered Foursquare places
    - Adding missing venues to database
    - Manual place addition
    """
    try:
        from ..services.place_data_service_v2 import enhanced_place_data_service

        # Check if place already exists
        existing = await db.execute(
            select(Place).where(Place.fsq_id == fsq_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Place already exists in database"
            )

        # Get venue details from Foursquare
        venue_details = await enhanced_place_data_service._get_foursquare_venue_details(fsq_id)
        if not venue_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Foursquare venue not found"
            )

        # Get venue photos
        photos = await enhanced_place_data_service._get_foursquare_venue_photos(fsq_id)

        # Create new place
        new_place = Place(
            name=venue_details.get('name', 'Unknown'),
            latitude=venue_details.get('location', {}).get('latitude'),
            longitude=venue_details.get('location', {}).get('longitude'),
            categories=','.join([cat.get('name', '')
                                for cat in venue_details.get('categories', [])]),
            rating=venue_details.get('rating'),
            phone=venue_details.get('tel'),
            website=venue_details.get('website'),
            external_id=fsq_id,
            data_source='foursquare',
            fsq_id=fsq_id,
            seed_source='fsq',
            place_metadata={
                'foursquare_id': fsq_id,
                'opening_hours': venue_details.get('hours', {}).get('display', ''),
                'price_level': venue_details.get('price'),
                'review_count': venue_details.get('stats', {}).get('total_ratings'),
                'photo_count': venue_details.get('stats', {}).get('total_photos'),
                'tip_count': venue_details.get('stats', {}).get('total_tips'),
                'photos': [
                    {
                        'url': photo.get('prefix') + 'original' + photo.get('suffix'),
                        'width': photo.get('width'),
                        'height': photo.get('height')
                    }
                    for photo in photos[:5]
                ],
                'promoted_at': datetime.now(timezone.utc).isoformat(),
                'promoted_by': current_user.id
            },
            last_enriched_at=datetime.now(timezone.utc)
        )

        db.add(new_place)
        await db.commit()
        await db.refresh(new_place)

        # Calculate quality score
        quality_score = enhanced_place_data_service._calculate_quality_score(
            new_place)

        return {
            "status": "success",
            "place_id": new_place.id,
            "name": new_place.name,
            "fsq_id": fsq_id,
            "quality_score": quality_score,
            "photos_count": len(photos),
            "promoted_at": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to promote Foursquare place: {str(e)}"
        )
