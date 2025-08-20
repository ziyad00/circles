from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, text

from ..database import get_db
from ..models import Place, CheckIn, SavedPlace, User, Review, Photo, CheckInPhoto
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
    ReviewCreate,
    ReviewResponse,
    PaginatedReviews,
    PlaceStats,
    PhotoResponse,
    PaginatedPhotos,
    CheckInPhotoResponse,
    EnhancedPlaceResponse,
)
from ..services.jwt_service import JWTService
from ..services.storage import StorageService
from ..utils import can_view_checkin


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
async def trending_places(
    city: str | None = None,
    category: str | None = None,
    hours: int = 24,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Basic ranking by number of check-ins in timeframe
    stmt = (
        select(Place)
        .join(CheckIn, CheckIn.place_id == Place.id)
        .where(CheckIn.created_at >= since)
    )
    if city:
        stmt = stmt.where(Place.city == city)
    if category:
        stmt = stmt.where(Place.categories.ilike(f"%{category}%"))

    # Order by count desc
    count_stmt = (
        select(CheckIn.place_id, func.count(CheckIn.id).label("cnt"))
        .where(CheckIn.created_at >= since)
        .group_by(CheckIn.place_id)
        .subquery()
    )
    stmt = (
        select(Place)
        .join(count_stmt, count_stmt.c.place_id == Place.id)
        .order_by(desc(count_stmt.c.cnt))
        .offset(offset)
        .limit(limit)
    )
    if city:
        stmt = stmt.where(Place.city == city)
    if category:
        stmt = stmt.where(Place.categories.ilike(f"%{category}%"))

    items = (await db.execute(stmt)).scalars().all()
    # count unique places with check-ins in window + filters
    total_q = select(func.count(func.distinct(CheckIn.place_id))).join(
        Place, CheckIn.place_id == Place.id).where(CheckIn.created_at >= since)
    if city:
        total_q = total_q.where(Place.city == city)
    if category:
        total_q = total_q.where(Place.categories.ilike(f"%{category}%"))
    total = (await db.execute(total_q)).scalar_one()
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


@router.get("/{place_id}/whos-here", response_model=PaginatedCheckIns)
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
        select(CheckIn)
        .where(CheckIn.place_id == place_id, CheckIn.created_at >= yesterday)
        .order_by(CheckIn.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    checkins = (await db.execute(stmt)).scalars().all()

    # Filter based on visibility and follow status
    from ..utils import can_view_checkin
    visible_checkins = []
    for checkin in checkins:
        if await can_view_checkin(checkin, current_user, db):
            visible_checkins.append(checkin)

    return PaginatedCheckIns(
        items=visible_checkins,
        total=len(visible_checkins),
        limit=limit,
        offset=offset
    )


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
    return check_in


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
