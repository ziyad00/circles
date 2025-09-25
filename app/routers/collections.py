from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_

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
# COLLECTION LISTING ENDPOINT (Used by frontend)
# ============================================================================


@router.get("/", response_model=list[CollectionResponse])
async def list_collections(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get current user's collections.

    **Authentication Required:** Yes
    """
    try:
        # Get user's collections
        collections_query = select(UserCollection).where(
            UserCollection.user_id == current_user.id
        ).order_by(UserCollection.name).offset(offset).limit(limit)

        result = await db.execute(collections_query)
        collections = result.scalars().all()

        # Convert to response format
        collection_list = []
        for collection in collections:
            # Get place count for this collection
            count_query = select(func.count()).select_from(
                select(UserCollectionPlace).where(
                    UserCollectionPlace.collection_id == collection.id
                ).subquery()
            )
            count_result = await db.execute(count_query)
            place_count = count_result.scalar()

            collection_resp = CollectionResponse(
                id=collection.id,
                user_id=collection.user_id,
                name=collection.name,
                description=collection.description,
                is_public=collection.is_public,
                visibility="public" if collection.is_public else "private",
                created_at=collection.created_at,
                updated_at=collection.updated_at,
            )
            collection_list.append(collection_resp)

        return collection_list

    except Exception as e:
        raise HTTPException(
            status_code=500, detail="Failed to get collections")

# ============================================================================
# COLLECTION CREATION ENDPOINT (Used by frontend)
# ============================================================================


@router.post("/", response_model=CollectionResponse)
async def create_collection(
    collection_create: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Create a new collection.

    **Authentication Required:** Yes
    """
    try:
        # Create new collection
        new_collection = UserCollection(
            user_id=current_user.id,
            name=collection_create.name,
            description=collection_create.description,
            is_public=collection_create.is_public,
        )

        db.add(new_collection)
        await db.commit()
        await db.refresh(new_collection)

        # Create response
        collection_resp = CollectionResponse(
            id=new_collection.id,
            user_id=new_collection.user_id,
            name=new_collection.name,
            description=new_collection.description,
            is_public=new_collection.is_public,
            visibility="public" if new_collection.is_public else "private",
            created_at=new_collection.created_at,
            updated_at=new_collection.updated_at,
        )

        return collection_resp

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to create collection")

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
        if not await can_view_collection(db, collection.user_id, current_user.id, "public" if collection.is_public else "private"):
            raise HTTPException(
                status_code=403, detail="Cannot view this collection")

        # Get collection places
        collection_places_query = select(UserCollectionPlace).where(
            UserCollectionPlace.collection_id == collection_id
        )
        collection_places_result = await db.execute(collection_places_query)
        collection_places = collection_places_result.scalars().all()
        
        if not collection_places:
            return PaginatedCollectionPlaces(items=[], total=0, limit=limit, offset=offset)
        
        # Get places from the collection places
        place_ids = [cp.place_id for cp in collection_places]
        places_query = select(Place).where(Place.id.in_(place_ids))
        places_result = await db.execute(places_query)
        places = places_result.scalars().all()

        # Convert to response format
        items = []
        for place in places:
            # Get sample photos from check-ins at this place
            photos_query = select(CheckInPhoto.url).join(CheckIn).where(
                and_(
                    CheckIn.place_id == place.id,
                    CheckInPhoto.url.isnot(None)
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

        return PaginatedCollectionPlaces(items=items, total=len(items), limit=limit, offset=offset)

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
