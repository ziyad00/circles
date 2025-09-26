from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    SavedPlace,
    UserCollection,
    UserCollectionPlace,
)


def normalize_collection_name(name: Optional[str]) -> str:
    """Normalize collection names, falling back to Favorites."""
    if not name:
        return "Favorites"
    normalized = name.strip()
    return normalized or "Favorites"


async def _get_collection(
    db: AsyncSession,
    user_id: int,
    name: str,
) -> Optional[UserCollection]:
    res = await db.execute(
        select(UserCollection).where(
            UserCollection.user_id == user_id,
            UserCollection.name == name,
        )
    )
    return res.scalar_one_or_none()


async def _get_or_create_collection(
    db: AsyncSession,
    user_id: int,
    name: str,
) -> UserCollection:
    collection = await _get_collection(db, user_id, name)
    if collection:
        return collection

    collection = UserCollection(
        user_id=user_id,
        name=name,
        is_public=True,
        visibility="public",
    )
    db.add(collection)
    await db.flush()
    return collection


async def _get_collection_place(
    db: AsyncSession,
    collection_id: int,
    place_id: int,
) -> Optional[UserCollectionPlace]:
    res = await db.execute(
        select(UserCollectionPlace).where(
            UserCollectionPlace.collection_id == collection_id,
            UserCollectionPlace.place_id == place_id,
        )
    )
    return res.scalar_one_or_none()


async def _ensure_collection_place(
    db: AsyncSession,
    collection: UserCollection,
    place_id: int,
    added_at: Optional[datetime] = None,
) -> UserCollectionPlace:
    existing = await _get_collection_place(db, collection.id, place_id)
    if existing:
        return existing

    association = UserCollectionPlace(
        collection_id=collection.id,
        place_id=place_id,
    )
    if added_at:
        association.added_at = added_at
    db.add(association)
    return association


async def ensure_default_collection(db: AsyncSession, user_id: int) -> UserCollection:
    """Ensure the user has a default Favorites collection."""
    return await _get_or_create_collection(db, user_id, "Favorites")


async def sync_saved_place_membership(
    db: AsyncSession,
    saved_place: SavedPlace,
    previous_collection_id: Optional[int] = None,
) -> UserCollectionPlace:
    """Ensure UserCollectionPlace rows reflect the SavedPlace state."""
    collection = saved_place.collection
    if not collection:
        name = normalize_collection_name(saved_place.list_name)
        collection = await _get_or_create_collection(db, saved_place.user_id, name)
        saved_place.collection = collection

    if previous_collection_id and previous_collection_id != collection.id:
        old_assoc = await _get_collection_place(db, previous_collection_id, saved_place.place_id)
        if old_assoc:
            await db.delete(old_assoc)

    association = await _ensure_collection_place(
        db, collection, saved_place.place_id, saved_place.created_at)
    return association


async def remove_saved_place_membership(
    db: AsyncSession,
    user_id: int,
    place_id: int,
    list_name: Optional[str] = None,
    collection_id: Optional[int] = None,
) -> None:
    collection: Optional[UserCollection] = None
    if collection_id is not None:
        res = await db.execute(
            select(UserCollection).where(
                UserCollection.id == collection_id,
                UserCollection.user_id == user_id,
            )
        )
        collection = res.scalar_one_or_none()
    elif list_name is not None:
        name = normalize_collection_name(list_name)
        collection = await _get_collection(db, user_id, name)
    else:
        return

    if not collection:
        return

    association = await _get_collection_place(db, collection.id, place_id)
    if association:
        await db.delete(association)


async def ensure_saved_place_entry(
    db: AsyncSession,
    user_id: int,
    place_id: int,
    list_name: Optional[str],
) -> SavedPlace:
    """Ensure a SavedPlace exists for the given collection name."""
    desired_name = normalize_collection_name(list_name)
    collection = await _get_or_create_collection(db, user_id, desired_name)
    res = await db.execute(
        select(SavedPlace).where(
            SavedPlace.user_id == user_id,
            SavedPlace.place_id == place_id,
        )
    )
    saved = res.scalar_one_or_none()
    if saved:
        previous_collection_id = saved.collection_id
        if saved.collection_id != collection.id:
            saved.collection = collection
        saved.list_name = collection.name
        await db.flush()
        await sync_saved_place_membership(db, saved, previous_collection_id)
        return saved

    saved = SavedPlace(
        user_id=user_id,
        place_id=place_id,
        collection=collection,
        list_name=collection.name,
    )
    db.add(saved)
    await db.flush()
    await db.refresh(saved)
    await sync_saved_place_membership(db, saved)
    return saved
