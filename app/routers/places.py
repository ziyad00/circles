from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from ..database import get_db
from ..models import Place, CheckIn, SavedPlace, User, Review
from ..schemas import (
    PlaceCreate,
    PlaceResponse,
    CheckInCreate,
    CheckInResponse,
    SavedPlaceCreate,
    SavedPlaceResponse,
    PaginatedPlaces,
    PaginatedSavedPlaces,
    PaginatedCheckIns,
    ReviewCreate,
    ReviewResponse,
    PaginatedReviews,
    PlaceStats,
)
from ..services.jwt_service import JWTService


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
    return place


@router.get("/search", response_model=PaginatedPlaces)
async def search_places(
    query: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    category: str | None = None,
    rating_min: float | None = None,
    limit: int = 20,
    offset: int = 0,
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


@router.get("/trending", response_model=PaginatedPlaces)
async def trending_places(
    city: str | None = None,
    category: str | None = None,
    hours: int = 24,
    limit: int = 10,
    offset: int = 0,
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


@router.get("/{place_id}", response_model=PlaceResponse)
async def get_place(place_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Place).where(Place.id == place_id))
    place = res.scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


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

    check_in = CheckIn(
        user_id=current_user.id,
        place_id=payload.place_id,
        note=payload.note,
        visibility=payload.visibility or "public",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(check_in)
    await db.commit()
    await db.refresh(check_in)
    return check_in


@router.get("/{place_id}/whos-here", response_model=list[CheckInResponse])
async def whos_here(
    place_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    now = datetime.now(timezone.utc)
    res = await db.execute(
        select(CheckIn)
        .where(
            CheckIn.place_id == place_id,
            CheckIn.expires_at >= now,
            CheckIn.visibility == "public",
        )
        .order_by(CheckIn.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return res.scalars().all()


@router.get("/me/check-ins", response_model=PaginatedCheckIns)
async def my_check_ins(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
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
    return PaginatedCheckIns(items=items, total=total, limit=limit, offset=offset)


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
    limit: int = 20,
    offset: int = 0,
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
    limit: int = 20,
    offset: int = 0,
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


@router.get("/{place_id}/stats", response_model=PlaceStats)
async def place_stats(place_id: int, db: AsyncSession = Depends(get_db)):
    # aggregate counts
    avg_q = select(func.avg(Review.rating)).where(Review.place_id == place_id)
    count_q = select(func.count(Review.id)).where(Review.place_id == place_id)
    now = datetime.now(timezone.utc)
    active_q = select(func.count(CheckIn.id)).where(
        CheckIn.place_id == place_id, CheckIn.expires_at >= now
    )
    avg = (await db.execute(avg_q)).scalar()
    count = (await db.execute(count_q)).scalar_one()
    active = (await db.execute(active_q)).scalar_one()
    return PlaceStats(
        place_id=place_id,
        average_rating=float(avg) if avg is not None else None,
        reviews_count=count,
        active_checkins=active,
    )


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
