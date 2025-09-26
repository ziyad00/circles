from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
import sqlalchemy as sa
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.collection_sync import ensure_default_collection
from ..services.jwt_service import JWTService
from ..services.storage import StorageService
from ..utils import can_view_collection
from ..models import (
    CheckIn,
    CheckInPhoto,
    Place,
    User,
    UserCollection,
    UserCollectionPlace,
    SavedPlace,
)
from ..schemas import (
    CollectionCreate,
    CollectionPlaceResponse,
    CollectionResponse,
    PaginatedCollectionPlaces,
    PaginatedCollections,
    VisibilityEnum,
)

router = APIRouter(prefix="/collections", tags=["collections"])


def _convert_to_signed_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http"):
        return url
    try:
        return StorageService.generate_signed_url(url)
    except Exception:
        return url


def _convert_to_signed_urls(urls: List[str]) -> List[str]:
    return [u for u in map(_convert_to_signed_url, urls)]


async def _fetch_collection_responses(
    db: AsyncSession,
    user_id: int,
    offset: int,
    limit: int,
) -> list[CollectionResponse]:
    await ensure_default_collection(db, user_id)

    base_stmt = (
        select(UserCollection)
        .where(UserCollection.user_id == user_id)
        .order_by(UserCollection.name)
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(base_stmt)
    collections = result.scalars().all()

    if not collections:
        return []

    collection_ids = [collection.id for collection in collections]

    counts_result = await db.execute(
        select(
            UserCollectionPlace.collection_id,
            func.count(UserCollectionPlace.id),
        )
        .where(UserCollectionPlace.collection_id.in_(collection_ids))
        .group_by(UserCollectionPlace.collection_id)
    )
    counts_map = {
        row[0]: row[1]
        for row in counts_result.fetchall()
    }

    responses: list[CollectionResponse] = []
    for collection in collections:
        photos_query = (
            select(CheckInPhoto.url)
            .join(CheckIn, CheckInPhoto.check_in_id == CheckIn.id)
            .join(
                UserCollectionPlace,
                UserCollectionPlace.place_id == CheckIn.place_id,
            )
            .where(
                and_(
                    UserCollectionPlace.collection_id == collection.id,
                    CheckInPhoto.url.isnot(None),
                )
            )
            .order_by(desc(CheckInPhoto.created_at))
            .limit(3)
        )

        photos_result = await db.execute(photos_query)
        photo_urls = [row[0] for row in photos_result.fetchall()]
        photo_urls = [p for p in _convert_to_signed_urls(photo_urls) if p]

        visibility_value = collection.visibility or (
            "public" if collection.is_public else "private"
        )

        responses.append(
            CollectionResponse(
                id=collection.id,
                user_id=collection.user_id,
                name=collection.name,
                description=collection.description,
                is_public=collection.is_public,
                visibility=VisibilityEnum(visibility_value),
                photo_urls=photo_urls,
                place_count=counts_map.get(collection.id, 0),
                created_at=collection.created_at,
                updated_at=collection.updated_at,
            )
        )

    return responses


@router.get("/", response_model=list[CollectionResponse])
async def list_collections(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
) -> list[CollectionResponse]:
    """Return the current user's collections."""
    return await _fetch_collection_responses(
        db=db,
        user_id=current_user.id,
        offset=offset,
        limit=limit,
    )


@router.post("/", response_model=CollectionResponse)
async def create_collection(
    collection_create: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
) -> CollectionResponse:
    """Create a new collection for the current user."""
    normalized_name = collection_create.name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Collection name cannot be empty")

    existing = await db.execute(
        select(UserCollection).where(
            UserCollection.user_id == current_user.id,
            func.lower(UserCollection.name) == normalized_name.lower(),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Collection name already exists")

    new_collection = UserCollection(
        user_id=current_user.id,
        name=normalized_name,
        description=collection_create.description,
        is_public=collection_create.is_public,
        visibility=collection_create.visibility.value
        if collection_create.visibility
        else ("public" if collection_create.is_public else "private"),
    )

    db.add(new_collection)
    await db.commit()
    await db.refresh(new_collection)

    return CollectionResponse(
        id=new_collection.id,
        user_id=new_collection.user_id,
        name=new_collection.name,
        description=new_collection.description,
        is_public=new_collection.is_public,
        visibility=VisibilityEnum(new_collection.visibility),
        created_at=new_collection.created_at,
        updated_at=new_collection.updated_at,
    )


@router.get("/{collection_id}/items", response_model=PaginatedCollectionPlaces)
async def get_collection_items(
    collection_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
) -> PaginatedCollectionPlaces:
    """Return places stored inside a specific collection."""
    collection_result = await db.execute(
        select(UserCollection).where(UserCollection.id == collection_id)
    )
    collection = collection_result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if not await can_view_collection(
        db,
        collection.user_id,
        current_user.id,
        collection.visibility or ("public" if collection.is_public else "private"),
    ):
        raise HTTPException(status_code=403, detail="Cannot view this collection")

    total = (
        await db.execute(
            select(func.count(UserCollectionPlace.id)).where(
                UserCollectionPlace.collection_id == collection.id
            )
        )
    ).scalar_one()

    places_stmt = (
        select(UserCollectionPlace, Place)
        .join(Place, UserCollectionPlace.place_id == Place.id)
        .where(UserCollectionPlace.collection_id == collection.id)
        .order_by(desc(UserCollectionPlace.added_at))
        .offset(offset)
        .limit(limit)
    )
    place_rows = await db.execute(places_stmt)

    items: list[CollectionPlaceResponse] = []
    for association, place in place_rows.all():
        photo_candidate = place.photo_url
        signed_photo = _convert_to_signed_url(photo_candidate)

        photos_query = (
            select(CheckInPhoto.url)
            .join(CheckIn, CheckInPhoto.check_in_id == CheckIn.id)
            .where(
                and_(
                    CheckIn.place_id == place.id,
                    CheckInPhoto.url.isnot(None),
                )
            )
            .order_by(desc(CheckInPhoto.created_at))
            .limit(3)
        )
        photos_result = await db.execute(photos_query)
        user_photo_urls = [row[0] for row in photos_result.fetchall()]
        signed_user_photos = _convert_to_signed_urls(user_photo_urls)
        combined_photo_urls: list[str] = []
        if signed_user_photos:
            combined_photo_urls.extend(signed_user_photos)
        elif signed_photo:
            combined_photo_urls.append(signed_photo)

        checkin_count = (
            await db.execute(
                select(func.count(CheckIn.id)).where(CheckIn.place_id == place.id)
            )
        ).scalar_one()

        items.append(
            CollectionPlaceResponse(
                id=association.id,
                collection_id=collection.id,
                place_id=place.id,
                place_name=place.name,
                place_address=place.address,
                place_city=place.city,
                place_latitude=place.latitude,
                place_longitude=place.longitude,
                place_rating=place.rating,
                place_photo_url=signed_photo,
                photo_url=signed_photo,
                photo_urls=combined_photo_urls,
                checkin_count=checkin_count or 0,
                user_checkin_photos=signed_user_photos,
                added_at=association.added_at or collection.created_at or datetime.now(timezone.utc),
            )
        )

    return PaginatedCollectionPlaces(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: int,
    collection_update: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
) -> CollectionResponse:
    """Update collection metadata."""
    collection_result = await db.execute(
        select(UserCollection).where(UserCollection.id == collection_id)
    )
    collection = collection_result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot update this collection")

    if collection_update.name is not None:
        new_name = collection_update.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Collection name cannot be empty")

        duplicate = await db.execute(
            select(UserCollection).where(
                UserCollection.user_id == current_user.id,
                func.lower(UserCollection.name) == new_name.lower(),
                UserCollection.id != collection.id,
            )
        )
        if duplicate.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Collection name already exists")
        collection.name = new_name
        await db.execute(
            sa.update(SavedPlace)
            .where(SavedPlace.collection_id == collection.id)
            .values(list_name=new_name)
        )

    if collection_update.description is not None:
        collection.description = collection_update.description

    if collection_update.is_public is not None:
        collection.is_public = collection_update.is_public
        collection.visibility = (
            "public" if collection_update.is_public else collection.visibility
        )

    if collection_update.visibility is not None:
        collection.visibility = collection_update.visibility.value

    collection.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(collection)

    return CollectionResponse(
        id=collection.id,
        user_id=collection.user_id,
        name=collection.name,
        description=collection.description,
        is_public=collection.is_public,
        visibility=VisibilityEnum(collection.visibility),
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


@router.get("/paginated", response_model=PaginatedCollections)
async def list_collections_paginated(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
) -> PaginatedCollections:
    """Optional paginated variant for clients that expect meta."""
    await ensure_default_collection(db, current_user.id)

    total = (
        await db.execute(
            select(func.count(UserCollection.id)).where(
                UserCollection.user_id == current_user.id
            )
        )
    ).scalar_one()

    items = await _fetch_collection_responses(
        db=db,
        user_id=current_user.id,
        offset=offset,
        limit=limit,
    )

    return PaginatedCollections(items=items, total=total, limit=limit, offset=offset)
