from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, text, or_, and_

from ..database import get_db
from ..models import Place, CheckIn, SavedPlace, User, Review, Photo, CheckInPhoto, CheckInCollection, CheckInCollectionItem
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
)
from ..services.jwt_service import JWTService
from ..services.storage import StorageService
from ..utils import can_view_checkin, haversine_distance
from ..routers.activity import create_checkin_activity


router = APIRouter(prefix="/places", tags=["places"])


@router.post("/", response_model=PlaceResponse)
async def create_place(payload: PlaceCreate, db: AsyncSession = Depends(get_db)):
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
        await db.execute(text("UPDATE places SET location = ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography WHERE id = :id"), {"lng": place.longitude, "lat": place.latitude, "id": place.id})
        await db.commit()
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
            distance_filter = func.ST_DWithin(
                Place.__table__.c.location,
                point.cast(text('geography')),
                filters.radius_km * 1000  # Convert km to meters
            )
            stmt = stmt.where(distance_filter)
            count_stmt = count_stmt.where(distance_filter)
        else:
            # Fallback to Haversine formula
            from ..utils import haversine_distance
            # This is a simplified approach - in production you'd want to optimize this
            # For now, we'll filter after the query
            pass

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
    items = (await db.execute(stmt)).scalars().all()

    # Apply distance filtering for non-PostGIS fallback
    if (filters.latitude is not None and filters.longitude is not None and
            filters.radius_km is not None and not getattr(app_settings, 'use_postgis', False)):
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
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trending places based on recent activity"""

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

    # Build trending score query
    # Score = (check-ins * 3) + (reviews * 2) + (photos * 1) + (unique users * 2)
    trending_subq = (
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

    return PaginatedPlaces(items=items, total=total, limit=limit, offset=offset)


@router.get("/trending/global", response_model=PaginatedPlaces)
async def get_global_trending_places(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get globally trending places (no auth required)"""

    # Use last 7 days for global trending
    window_start = datetime.now(timezone.utc) - timedelta(days=7)

    # Build trending score query
    trending_subq = (
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
    if app_settings.use_postgis:
        # Use ST_DWithin and ST_Distance for efficient geo query
        point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
        # Count
        total_q = select(func.count(Place.id)).where(
            Place.latitude.is_not(None), Place.longitude.is_not(None), func.ST_DWithin(
                Place.__table__.c.location, point.cast(text('geography')), radius_m)
        )
        total = (await db.execute(total_q)).scalar_one()
        stmt = (
            select(Place)
            .where(Place.latitude.is_not(None), Place.longitude.is_not(None), func.ST_DWithin(Place.__table__.c.location, point.cast(text('geography')), radius_m))
            .order_by(func.ST_Distance(Place.__table__.c.location, point.cast(text('geography'))).asc())
            .offset(offset)
            .limit(limit)
        )
        items = (await db.execute(stmt)).scalars().all()
        return PaginatedPlaces(items=items, total=total, limit=limit, offset=offset)
    else:
        # Haversine fallback
        lat_rad = func.radians(lat)
        lng_rad = func.radians(lng)
        place_lat = func.radians(Place.latitude)
        place_lng = func.radians(Place.longitude)
        arg = (
            func.cos(lat_rad) * func.cos(place_lat) *
            func.cos(place_lng - lng_rad)
            + func.sin(lat_rad) * func.sin(place_lat)
        )
        arg_clamped = func.greatest(-1.0, func.least(1.0, arg))
        distance_m = 6371000 * func.acos(arg_clamped)

        total_q = (
            select(func.count(Place.id))
            .where(Place.latitude.is_not(None), Place.longitude.is_not(None))
            .where(distance_m <= radius_m)
        )
        total = (await db.execute(total_q)).scalar_one()

        stmt = (
            select(Place)
            .where(Place.latitude.is_not(None), Place.longitude.is_not(None))
            .where(distance_m <= radius_m)
            .order_by(distance_m.asc())
            .offset(offset)
            .limit(limit)
        )
        items = (await db.execute(stmt)).scalars().all()
        return PaginatedPlaces(items=items, total=total, limit=limit, offset=offset)


@router.get("/{place_id}", response_model=EnhancedPlaceResponse)
async def get_place(
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get place details with enhanced statistics and user-specific data"""
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

    # Create enhanced response
    return EnhancedPlaceResponse(
        id=place.id,
        name=place.name,
        address=place.address,
        city=place.city,
        neighborhood=place.neighborhood,
        latitude=place.latitude,
        longitude=place.longitude,
        categories=place.categories,
        rating=place.rating,
        created_at=place.created_at,
        stats=stats,
        current_checkins=current_checkins,
        total_checkins=total_checkins,
        recent_reviews=recent_reviews,
        photos_count=photos_count,
        is_checked_in=is_checked_in,
        is_saved=is_saved
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


@router.get("/{place_id}/stats/enhanced", response_model=EnhancedPlaceStats)
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
    """Get who's currently checked in at this place (last 24h)"""
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
        select(CheckIn, User.name, User.avatar_url)
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
    for checkin, user_name, avatar_url in rows:
        if await can_view_checkin(db, checkin.user_id, current_user.id, checkin.visibility):
            # photos
            res_ph = await db.execute(select(CheckInPhoto).where(CheckInPhoto.check_in_id == checkin.id).order_by(CheckInPhoto.created_at.asc()))
            urls = [p.url for p in res_ph.scalars().all()]
            items.append(
                WhosHereItem(
                    check_in_id=checkin.id,
                    user_id=checkin.user_id,
                    user_name=user_name or f"User {checkin.user_id}",
                    user_avatar_url=avatar_url,
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
        current_user, "checkins_default_visibility", "public")
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
        print(f"Failed to create activity for check-in {check_in.id}: {e}")

    return check_in


@router.post("/check-ins/full", response_model=CheckInResponse)
async def create_check_in_full(
    place_id: int = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    note: str | None = Form(None),
    visibility: str | None = Form(None),
    # JSON array ("[1,2]") or comma-separated string
    collection_ids: str | None = Form(None),
    files: list[UploadFile] | None = File(None),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
        current_user, "checkins_default_visibility", "public")
    check_in = CheckIn(
        user_id=current_user.id,
        place_id=place_id,
        note=note,
        visibility=visibility or default_vis,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(check_in)
    await db.flush()  # get check_in.id before committing

    # Save photos if provided
    if files:
        for file in files:
            if not file:
                continue
            content = await file.read()
            try:
                url_path = await StorageService.save_checkin_photo(check_in.id, file.filename or "upload.jpg", content)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            db.add(CheckInPhoto(check_in_id=check_in.id, url=url_path))
            # keep backward-compatible single photo_url set to last uploaded
            check_in.photo_url = url_path

    # Add to collections if provided
    if collection_ids:
        import json
        ids: list[int] = []
        try:
            parsed = json.loads(collection_ids)
            if isinstance(parsed, list):
                ids = [int(x) for x in parsed]
        except Exception:
            # fallback: comma-separated
            parts = [p.strip() for p in collection_ids.split(",") if p.strip()]
            ids = [int(p) for p in parts if p.isdigit()]
        if ids:
            # verify ownership of collections
            owned_q = await db.execute(
                select(CheckInCollection.id).where(
                    CheckInCollection.user_id == current_user.id,
                    CheckInCollection.id.in_(ids),
                )
            )
            owned = {row[0] for row in owned_q.fetchall()}
            for cid in owned:
                db.add(CheckInCollectionItem(
                    collection_id=cid, check_in_id=check_in.id))

    await db.commit()
    await db.refresh(check_in)

    # enrich response with photo_urls
    res_ph = await db.execute(
        select(CheckInPhoto).where(CheckInPhoto.check_in_id ==
                                   check_in.id).order_by(CheckInPhoto.created_at.asc())
    )
    photo_urls = [p.url for p in res_ph.scalars().all()]

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
        print(f"Failed to create activity for check-in {check_in.id}: {e}")

    return CheckInResponse(
        id=check_in.id,
        user_id=check_in.user_id,
        place_id=check_in.place_id,
        note=check_in.note,
        visibility=check_in.visibility,
        created_at=check_in.created_at,
        expires_at=check_in.expires_at,
        photo_url=check_in.photo_url,
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
    except ValueError as e:
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
    return CheckInResponse(
        id=checkin.id,
        user_id=checkin.user_id,
        place_id=checkin.place_id,
        note=checkin.note,
        visibility=checkin.visibility,
        created_at=checkin.created_at,
        expires_at=checkin.expires_at,
        photo_url=checkin.photo_url,
        photo_urls=photo_urls,
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
    return [CheckInPhotoResponse(id=p.id, check_in_id=p.check_in_id, url=p.url, created_at=p.created_at) for p in photos]


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
        result.append(
            CheckInResponse(
                id=ci.id,
                user_id=ci.user_id,
                place_id=ci.place_id,
                note=ci.note,
                visibility=ci.visibility,
                created_at=ci.created_at,
                expires_at=ci.expires_at,
                photo_url=ci.photo_url,
                photo_urls=urls,
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
        enriched.append(
            CheckInResponse(
                id=ci.id,
                user_id=ci.user_id,
                place_id=ci.place_id,
                note=ci.note,
                visibility=ci.visibility,
                created_at=ci.created_at,
                expires_at=ci.expires_at,
                photo_url=ci.photo_url,
                photo_urls=urls,
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

    saved_new = SavedPlace(
        user_id=current_user.id,
        place_id=payload.place_id,
        list_name=payload.list_name,
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
):
    total = (
        await db.execute(
            select(func.count(SavedPlace.id)).where(
                SavedPlace.user_id == current_user.id)
        )
    ).scalar_one()
    res = await db.execute(
        select(SavedPlace)
        .where(SavedPlace.user_id == current_user.id)
        .offset(offset)
        .limit(limit)
    )
    items = res.scalars().all()
    return PaginatedSavedPlaces(items=items, total=total, limit=limit, offset=offset)


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
