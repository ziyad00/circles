from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..services.jwt_service import JWTService
from ..models import CheckIn, CheckInCollection, CheckInCollectionItem
from ..schemas import (
    CollectionCreate,
    CollectionResponse,
    PaginatedCollections,
    CollectionItemResponse,
)


router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("/", response_model=CollectionResponse)
async def create_collection(
    payload: CollectionCreate,
    current_user = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # default visibility from user settings if not provided
    visibility = payload.visibility if payload.visibility is not None else getattr(current_user, "collections_default_visibility", "public")
    coll = CheckInCollection(user_id=current_user.id, name=payload.name, visibility=visibility)
    db.add(coll)
    await db.commit()
    await db.refresh(coll)
    return coll


@router.get("/", response_model=PaginatedCollections)
async def list_collections(
    current_user = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    total = (
        await db.execute(
            select(func.count(CheckInCollection.id)).where(CheckInCollection.user_id == current_user.id)
        )
    ).scalar_one()
    res = await db.execute(
        select(CheckInCollection)
        .where(CheckInCollection.user_id == current_user.id)
        .order_by(CheckInCollection.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = res.scalars().all()
    return PaginatedCollections(items=items, total=total, limit=limit, offset=offset)


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def rename_collection(
    collection_id: int,
    payload: CollectionCreate,
    current_user = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(CheckInCollection).where(CheckInCollection.id == collection_id)
    )
    coll = res.scalars().first()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")
    if coll.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    coll.name = payload.name
    if payload.visibility is not None:
        coll.visibility = payload.visibility
    await db.commit()
    await db.refresh(coll)
    return coll


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: int,
    current_user = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(CheckInCollection).where(CheckInCollection.id == collection_id)
    )
    coll = res.scalars().first()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")
    if coll.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.delete(coll)
    await db.commit()
    return None


@router.post("/{collection_id}/items/{check_in_id}", response_model=CollectionItemResponse)
async def add_checkin_to_collection(
    collection_id: int,
    check_in_id: int,
    current_user = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # check collection
    res = await db.execute(select(CheckInCollection).where(CheckInCollection.id == collection_id))
    coll = res.scalars().first()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")
    if coll.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    # check check-in ownership
    res_ci = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    ci = res_ci.scalars().first()
    if not ci:
        raise HTTPException(status_code=404, detail="Check-in not found")
    if ci.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to add this check-in")
    # prevent duplicates
    existing = await db.execute(
        select(CheckInCollectionItem).where(
            CheckInCollectionItem.collection_id == collection_id,
            CheckInCollectionItem.check_in_id == check_in_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Already in collection")

    item = CheckInCollectionItem(collection_id=collection_id, check_in_id=check_in_id)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/{collection_id}/items", response_model=list[CollectionItemResponse])
async def list_collection_items(
    collection_id: int,
    current_user = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(CheckInCollection).where(CheckInCollection.id == collection_id))
    coll = res.scalars().first()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")
    # visibility enforcement: owner sees always; others based on collection.visibility
    if coll.user_id != current_user.id:
        if coll.visibility == "private":
            raise HTTPException(status_code=403, detail="Not allowed")
        if coll.visibility == "friends":
            # friends means followers of the owner
            from ..models import Follow
            fol = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == coll.user_id))
            if fol.scalars().first() is None:
                raise HTTPException(status_code=403, detail="Not allowed")

    res_items = await db.execute(
        select(CheckInCollectionItem)
        .where(CheckInCollectionItem.collection_id == collection_id)
        .order_by(CheckInCollectionItem.created_at.desc())
    )
    return res_items.scalars().all()


@router.delete("/{collection_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_collection_item(
    collection_id: int,
    item_id: int,
    current_user = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(CheckInCollection).where(CheckInCollection.id == collection_id))
    coll = res.scalars().first()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")
    if coll.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    res_item = await db.execute(
        select(CheckInCollectionItem).where(
            CheckInCollectionItem.id == item_id,
            CheckInCollectionItem.collection_id == collection_id,
        )
    )
    item = res_item.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
    await db.commit()
    return None


