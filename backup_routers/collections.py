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
                # Fallback to original URL if signing fails
                signed_urls.append(url)
        else:
            # Already a full URL (e.g., from FSQ or local storage)
            signed_urls.append(url)
    return signed_urls


router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("/summary", response_model=list[dict])
async def list_collections_summary(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Minimal summary for user's collections with random photos.

    Returns list of: { id, name, count, photos[<=4] }
    """
    # Aggregate counts and place_ids per collection
    result = await db.execute(
        select(
            UserCollection.id,
            UserCollection.name,
            func.count(UserCollectionPlace.id).label("count"),
            func.array_agg(UserCollectionPlace.place_id).label("place_ids"),
        )
        .join(
            UserCollectionPlace,
            UserCollection.id == UserCollectionPlace.collection_id,
            isouter=True,
        )
        .where(UserCollection.user_id == current_user.id)
        .group_by(UserCollection.id, UserCollection.name)
        .order_by(desc(UserCollection.created_at))
    )

    rows = result.all()
    collections: list[dict] = []
    for col_id, name, count, place_ids in rows:
        photos: list[str] = []
        place_ids = [pid for pid in (place_ids or []) if pid is not None]
        if place_ids:
            # Prefer place photos
            photos_res = await db.execute(
                select(Photo.url)
                .where(Photo.place_id.in_(place_ids))
                .order_by(func.random())
                .limit(4)
            )
            photos = list(photos_res.scalars().all())

            # Fallback to general check-in photos if no place photos exist
            if not photos:
                ciph_res = await db.execute(
                    select(CheckInPhoto.url)
                    .join(CheckIn, CheckInPhoto.check_in_id == CheckIn.id)
                    .where(CheckIn.place_id.in_(place_ids))
                    .order_by(func.random())
                    .limit(4)
                )
                photos = list(ciph_res.scalars().all())

        collections.append(
            {
                "id": col_id,
                "name": name,
                "count": int(count or 0),
                "photos": _convert_to_signed_urls(photos),
            }
        )

    return collections


@router.post("/", response_model=CollectionResponse)
async def create_collection(
    payload: CollectionCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new user collection.

    **Authentication Required:** Yes

    **Features:**
    - Create custom collections to organize places
    - Public or private visibility
    - Add description for collection purpose
    """
    # Check if collection name already exists for this user
    existing = await db.execute(
        select(UserCollection).where(
            UserCollection.user_id == current_user.id,
            UserCollection.name == payload.name
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Collection with this name already exists"
        )

    # Handle backward compatibility: visibility overrides is_public if provided
    if payload.visibility is not None:
        visibility = payload.visibility.value
        is_public = (visibility == "public")
    else:
        visibility = "public" if payload.is_public else "private"
        is_public = payload.is_public

    collection = UserCollection(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        is_public=is_public,
        visibility=visibility
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return collection


@router.get("/", response_model=PaginatedCollections)
async def list_user_collections(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Get current user's collections.

    **Authentication Required:** Yes

    Returns all collections created by the current user.
    """
    total = (
        await db.execute(
            select(func.count(UserCollection.id)).where(
                UserCollection.user_id == current_user.id
            )
        )
    ).scalar_one()

    result = await db.execute(
        select(UserCollection)
        .where(UserCollection.user_id == current_user.id)
        .order_by(desc(UserCollection.created_at))
        .offset(offset)
        .limit(limit)
    )
    collections = result.scalars().all()

    return PaginatedCollections(
        items=collections,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific collection by ID.

    **Authentication Required:** Yes

    Returns collection details if owned by current user or if public.
    """
    result = await db.execute(
        select(UserCollection).where(UserCollection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Check ownership or visibility permissions
    if collection.user_id != current_user.id:
        visibility = getattr(collection, 'visibility', 'public' if collection.is_public else 'private')
        can_view = await can_view_collection(db, collection.user_id, current_user.id, visibility)
        if not can_view:
            raise HTTPException(status_code=403, detail="Collection is private")

    return collection


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: int,
    payload: CollectionCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a collection.

    **Authentication Required:** Yes

    Only collection owner can update their collections.
    """
    result = await db.execute(
        select(UserCollection).where(UserCollection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this collection")

    # Check if new name conflicts with existing collection
    if payload.name != collection.name:
        existing = await db.execute(
            select(UserCollection).where(
                UserCollection.user_id == current_user.id,
                UserCollection.name == payload.name,
                UserCollection.id != collection_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Collection with this name already exists"
            )

    collection.name = payload.name
    collection.description = payload.description

    # Handle backward compatibility: visibility overrides is_public if provided
    if payload.visibility is not None:
        visibility = payload.visibility.value
        is_public = (visibility == "public")
    else:
        visibility = "public" if payload.is_public else "private"
        is_public = payload.is_public

    collection.is_public = is_public
    collection.visibility = visibility

    await db.commit()
    await db.refresh(collection)
    return collection


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a collection.

    **Authentication Required:** Yes

    Only collection owner can delete their collections.
    """
    result = await db.execute(
        select(UserCollection).where(UserCollection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this collection")

    await db.delete(collection)
    await db.commit()


@router.post("/{collection_id}/places/{place_id}", response_model=dict)
async def add_place_to_collection(
    collection_id: int,
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a place to a collection.

    **Authentication Required:** Yes

    Only collection owner can add places to their collections.
    """
    # Verify collection exists and user owns it
    collection_result = await db.execute(
        select(UserCollection).where(UserCollection.id == collection_id)
    )
    collection = collection_result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this collection")

    # Verify place exists
    place_result = await db.execute(select(Place).where(Place.id == place_id))
    place = place_result.scalar_one_or_none()

    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Check if place is already in collection
    existing = await db.execute(
        select(UserCollectionPlace).where(
            UserCollectionPlace.collection_id == collection_id,
            UserCollectionPlace.place_id == place_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail="Place already in collection")

    saved_place = await ensure_saved_place_entry(
        db, current_user.id, place_id, collection.name)
    await db.flush()

    association_res = await db.execute(
        select(UserCollectionPlace).where(
            UserCollectionPlace.collection_id == collection_id,
            UserCollectionPlace.place_id == place_id
        )
    )
    association = association_res.scalar_one_or_none()
    if association is None:
        association = await sync_saved_place_membership(db, saved_place)
    if association is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to persist collection membership",
        )

    await db.commit()
    await db.refresh(saved_place)
    await db.refresh(association)

    return {
        "message": "Place added to collection",
        "id": association.id,
    }


@router.delete("/{collection_id}/places/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_place_from_collection(
    collection_id: int,
    place_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove a place from a collection.

    **Authentication Required:** Yes

    Only collection owner can remove places from their collections.
    """
    # Verify collection exists and user owns it
    collection_result = await db.execute(
        select(UserCollection).where(UserCollection.id == collection_id)
    )
    collection = collection_result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this collection")

    # Find and remove the place from collection
    result = await db.execute(
        select(UserCollectionPlace).where(
            UserCollectionPlace.collection_id == collection_id,
            UserCollectionPlace.place_id == place_id
        )
    )
    collection_place = result.scalar_one_or_none()

    if not collection_place:
        raise HTTPException(
            status_code=404, detail="Place not found in collection")

    saved_lookup = await db.execute(
        select(SavedPlace).where(
            SavedPlace.user_id == current_user.id,
            SavedPlace.place_id == place_id,
        )
    )
    saved_place = saved_lookup.scalar_one_or_none()

    if saved_place:
        await remove_saved_place_membership(
            db, current_user.id, place_id, saved_place.list_name)
        await db.delete(saved_place)
    else:
        await remove_saved_place_membership(
            db, current_user.id, place_id, collection.name)

    await db.commit()


@router.get("/{collection_id}/places", response_model=PaginatedCollectionPlaces)
async def get_collection_places(
    collection_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Get places in a collection with enhanced data.

    **Authentication Required:** Yes

    Returns places with check-in stats, photos, and user check-in photos.
    """
    # Verify collection exists and user can access it
    collection_result = await db.execute(
        select(UserCollection).where(UserCollection.id == collection_id)
    )
    collection = collection_result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection.user_id != current_user.id:
        visibility = getattr(collection, 'visibility', 'public' if collection.is_public else 'private')
        can_view = await can_view_collection(db, collection.user_id, current_user.id, visibility)
        if not can_view:
            raise HTTPException(status_code=403, detail="Collection is private")

    # Get total count
    total = (
        await db.execute(
            select(func.count(UserCollectionPlace.id)).where(
                UserCollectionPlace.collection_id == collection_id
            )
        )
    ).scalar_one()

    # Get places with enhanced data
    query = (
        select(
            UserCollectionPlace,
            Place.name,
            Place.address,
            Place.city,
            Place.latitude,
            Place.longitude,
            Place.rating,
            func.count(CheckIn.id).label('checkin_count')
        )
        .join(Place, UserCollectionPlace.place_id == Place.id)
        .outerjoin(CheckIn, CheckIn.place_id == Place.id)
        .where(UserCollectionPlace.collection_id == collection_id)
        .group_by(
            UserCollectionPlace.id,
            Place.id,
            Place.name,
            Place.address,
            Place.city,
            Place.latitude,
            Place.longitude,
            Place.rating
        )
        .order_by(desc(UserCollectionPlace.added_at))
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    items = result.all()

    collection_places = []
    for (
        collection_place,
        place_name,
        address,
        city,
        latitude,
        longitude,
        rating,
        checkin_count
    ) in items:

        # Get place photo (latest photo from place)
        place_photo_result = await db.execute(
            select(Photo.url)
            .where(Photo.place_id == collection_place.place_id)
            .order_by(desc(Photo.created_at))
            .limit(1)
        )
        place_photo_url = place_photo_result.scalar_one_or_none()
        if place_photo_url:
            place_photo_url = _convert_to_signed_urls([place_photo_url])[0]

        # Get user's check-in photos from this place
        user_checkin_photos_result = await db.execute(
            select(CheckInPhoto.url)
            .join(CheckIn, CheckInPhoto.check_in_id == CheckIn.id)
            .where(
                CheckIn.place_id == collection_place.place_id,
                CheckIn.user_id == current_user.id
            )
            .order_by(desc(CheckInPhoto.created_at))
            .limit(10)
        )
        user_checkin_photo_urls = user_checkin_photos_result.scalars().all()
        user_checkin_photos = _convert_to_signed_urls(
            list(user_checkin_photo_urls))

        collection_places.append(CollectionPlaceResponse(
            id=collection_place.id,
            collection_id=collection_place.collection_id,
            place_id=collection_place.place_id,
            place_name=place_name,
            place_address=address,
            place_city=city,
            place_latitude=latitude,
            place_longitude=longitude,
            place_rating=rating,
            place_photo_url=place_photo_url,
            checkin_count=checkin_count or 0,
            user_checkin_photos=user_checkin_photos,
            added_at=collection_place.added_at
        ))

    return PaginatedCollectionPlaces(
        items=collection_places,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{collection_id}/items", response_model=PaginatedCollectionPlaces)
async def get_collection_items(
    collection_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Alias of /collections/{collection_id}/places for backward compatibility."""
    return await get_collection_places(
        collection_id=collection_id,
        current_user=current_user,
        db=db,
        limit=limit,
        offset=offset,
    )


@router.get("/{collection_id}/items/list", response_model=list[dict])
async def get_collection_items_list(
    collection_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Minimal, non-paginated items list for a collection (stable shape).

    Returns list of dicts with basic place info and photos.
    """
    # Verify access to collection
    col_res = await db.execute(
        select(UserCollection).where(UserCollection.id == collection_id)
    )
    collection = col_res.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    if collection.user_id != current_user.id:
        visibility = getattr(collection, 'visibility', 'public' if collection.is_public else 'private')
        can_view = await can_view_collection(db, collection.user_id, current_user.id, visibility)
        if not can_view:
            raise HTTPException(status_code=403, detail="Collection is private")

    # Fetch places in this collection (no pagination)
    places_query = (
        select(
            UserCollectionPlace,
            Place.name,
            Place.address,
            Place.city,
            Place.latitude,
            Place.longitude,
            Place.rating,
            Place.description,
            Place.categories,
        )
        .join(Place, UserCollectionPlace.place_id == Place.id)
        .where(UserCollectionPlace.collection_id == collection_id)
        .order_by(desc(UserCollectionPlace.added_at))
    )
    result = await db.execute(places_query)
    rows = result.all()

    items: list[dict] = []
    for (
        uc_place,
        place_name,
        address,
        city,
        latitude,
        longitude,
        rating,
        description,
        categories,
    ) in rows:
        # Gather up to 10 place photos
        photos_res = await db.execute(
            select(Photo.url)
            .where(Photo.place_id == uc_place.place_id)
            .order_by(desc(Photo.created_at))
            .limit(10)
        )
        photos = _convert_to_signed_urls(list(photos_res.scalars().all()))

        items.append(
            {
                "collection_place_id": uc_place.id,
                "place_id": uc_place.place_id,
                "place_name": place_name,
                "address": address,
                "city": city,
                "latitude": latitude,
                "longitude": longitude,
                "rating": rating,
                "description": description,
                "categories": categories,
                "photos": photos,
                "added_at": uc_place.added_at,
            }
        )

    return items
