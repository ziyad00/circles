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

    collection = UserCollection(user_id=user_id, name=name, is_public=True)
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


async def sync_saved_place_membership(
    db: AsyncSession,
    saved_place: SavedPlace,
    previous_name: Optional[str] = None,
) -> UserCollectionPlace:
    """Ensure UserCollectionPlace rows reflect the SavedPlace state."""
    new_name = normalize_collection_name(saved_place.list_name)
    if previous_name is not None:
        old_name = normalize_collection_name(previous_name)
    else:
        old_name = None

    if old_name and old_name != new_name:
        old_collection = await _get_collection(db, saved_place.user_id, old_name)
        if old_collection:
            existing = await _get_collection_place(
                db, old_collection.id, saved_place.place_id)
            if existing:
                await db.delete(existing)

    collection = await _get_or_create_collection(
        db, saved_place.user_id, new_name)
    association = await _ensure_collection_place(
        db, collection, saved_place.place_id, saved_place.created_at)
    return association


async def remove_saved_place_membership(
    db: AsyncSession,
    user_id: int,
    place_id: int,
    list_name: Optional[str],
) -> None:
    name = normalize_collection_name(list_name)
    collection = await _get_collection(db, user_id, name)
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
    res = await db.execute(
        select(SavedPlace).where(
            SavedPlace.user_id == user_id,
            SavedPlace.place_id == place_id,
        )
    )
    saved = res.scalar_one_or_none()
    if saved:
        current_name = normalize_collection_name(saved.list_name)
        if current_name != desired_name:
            previous = saved.list_name
            saved.list_name = desired_name
            await db.flush()
            await sync_saved_place_membership(db, saved, previous)
        else:
            await sync_saved_place_membership(db, saved)
        return saved

    saved = SavedPlace(
        user_id=user_id,
        place_id=place_id,
        list_name=desired_name,
    )
    db.add(saved)
    await db.flush()
    await db.refresh(saved)
    await sync_saved_place_membership(db, saved)
    return saved
