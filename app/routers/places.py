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
async def whos_here(place_id: int, db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    res = await db.execute(
        select(CheckIn).where(CheckIn.place_id ==
                              place_id, CheckIn.created_at >= since)
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
    # confirm place exists
    if not (await db.execute(select(Place).where(Place.id == place_id))).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Place not found")
    review = Review(
        user_id=current_user.id,
        place_id=place_id,
        rating=payload.rating,
        text=payload.text,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


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

    saved = SavedPlace(
        user_id=current_user.id,
        place_id=payload.place_id,
        list_name=payload.list_name,
    )
    db.add(saved)
    await db.commit()
    await db.refresh(saved)
    return saved


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
