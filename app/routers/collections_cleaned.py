from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from ..database import get_db
from ..services.jwt_service import JWTService
from ..services.storage import StorageService
from ..utils import can_view_collection
from ..services.collection_sync import (
    ensure_saved_place_entry,
    remove_saved_place_membership,
    sync_saved_place_membership,
)
from ..models import User, UserCollection, UserCollectionPlace, Place, CheckIn, CheckInPhoto, Photo, SavedPlace
from ..schemas import (
    CollectionCreate,
    CollectionResponse,
    CollectionPlaceResponse,
    PaginatedCollections,
    PaginatedCollectionPlaces,
)

router = APIRouter(prefix="/collections", tags=["collections"])

# ============================================================================
# COLLECTION ITEMS ENDPOINT (Used by frontend)
# ============================================================================


@router.get("/{collection_id}/items", response_model=PaginatedCollectionPlaces)
async def get_collection_items(
    collection_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get items (places) in a specific collection.

    **Authentication Required:** Yes
    """
    try:
        # Get collection
        collection_query = select(UserCollection).where(
            UserCollection.id == collection_id)
        collection_result = await db.execute(collection_query)
        collection = collection_result.scalar_one_or_none()

        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        # Check if user can view this collection
        if not can_view_collection(current_user, collection):
            raise HTTPException(
                status_code=403, detail="Cannot view this collection")

        # Get collection places
        places_query = select(Place).join(UserCollectionPlace).where(
            UserCollectionPlace.collection_id == collection_id
        ).order_by(desc(UserCollectionPlace.created_at))

        # Get total count
        count_query = select(func.count()).select_from(places_query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        places_query = places_query.offset(offset).limit(limit)
        places_result = await db.execute(places_query)
        places = places_result.scalars().all()

        # Convert to response format
        items = []
        for place in places:
            # Get sample photos from check-ins at this place
            photos_query = select(CheckInPhoto.photo_url).join(CheckIn).where(
                and_(
                    CheckIn.place_id == place.id,
                    CheckInPhoto.photo_url.isnot(None)
                )
            ).limit(3)
            photos_result = await db.execute(photos_query)
            photo_urls = [row[0] for row in photos_result.fetchall()]

            place_resp = CollectionPlaceResponse(
                id=place.id,
                name=place.name,
                address=place.address,
                city=place.city,
                country=place.country,
                latitude=place.latitude,
                longitude=place.longitude,
                categories=place.categories,
                rating=place.rating,
                photo_urls=photo_urls,
                added_at=None,  # TODO: Get from UserCollectionPlace
            )
            items.append(place_resp)

        return PaginatedCollectionPlaces(items=items, total=total, limit=limit, offset=offset)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="Failed to get collection items")

# ============================================================================
# COLLECTION UPDATE ENDPOINT (Used by frontend)
# ============================================================================


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: int,
    collection_update: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Update a collection's details.

    **Authentication Required:** Yes
    """
    try:
        # Get collection
        collection_query = select(UserCollection).where(
            UserCollection.id == collection_id)
        collection_result = await db.execute(collection_query)
        collection = collection_result.scalar_one_or_none()

        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        # Check if user owns this collection
        if collection.user_id != current_user.id:
            raise HTTPException(
                status_code=403, detail="Cannot update this collection")

        # Update collection
        if collection_update.name is not None:
            collection.name = collection_update.name
        if collection_update.description is not None:
            collection.description = collection_update.description
        if collection_update.is_public is not None:
            collection.is_public = collection_update.is_public

        collection.updated_at = func.now()

        await db.commit()
        await db.refresh(collection)

        # Get place count
        count_query = select(func.count()).select_from(
            select(UserCollectionPlace).where(
                UserCollectionPlace.collection_id == collection_id).subquery()
        )
        count_result = await db.execute(count_query)
        place_count = count_result.scalar()

        # Create response
        collection_resp = CollectionResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            is_public=collection.is_public,
            place_count=place_count,
            created_at=collection.created_at,
            updated_at=collection.updated_at,
        )

        return collection_resp

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to update collection")
