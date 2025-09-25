from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Query
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_, or_

from ..database import get_db
from ..services.jwt_service import JWTService
from ..services.storage import StorageService, _validate_image_or_raise
from ..services.block_service import has_block_between, has_user_blocked
from ..utils import (
    can_view_checkin,
    haversine_distance,
    can_view_profile,
    can_view_stats,
    can_view_follower_list,
    can_view_following_list,
    should_appear_in_search
)
from ..models import (
    User,
    CheckIn,
    CheckInPhoto,
    Photo,
    Follow,
    UserInterest,
    SavedPlace,
    CheckInLike,
    CheckInComment,
    Review,
    Place,
    DMThread,
    DMParticipantState,
)
from ..schemas import (
    UserUpdate,
    PublicUserResponse,
    PublicUserSearchResponse,
    InterestCreate,
    InterestResponse,
    PaginatedCheckIns,
    CheckInResponse,
    PaginatedMedia,
    ProfileStats,
    UserSearchFilters,
    AvailabilityStatus,
    AvailabilityMode,
)
from .dms_ws import manager


router = APIRouter(prefix="/users", tags=["users"])


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


def _convert_single_to_signed_url(photo_url: str | None) -> str | None:
    """
    Convert a single S3 key or S3 URL to signed URL for secure access.
    """
    if not photo_url:
        return None

    if not photo_url.startswith('http'):
        # This is an S3 key, convert to signed URL
        try:
            return StorageService.generate_signed_url(photo_url)
        except Exception as e:
            # Fallback to original URL if signing fails
            return photo_url
    elif 's3.amazonaws.com' in photo_url or 'circles-media-259c' in photo_url:
        # This is an S3 URL, extract the key and convert to signed URL
        try:
            # Extract S3 key from URL like: https://circles-media-259c.s3.amazonaws.com/checkins/39/test_photo.jpg
            # or: https://s3.amazonaws.com/circles-media-259c/checkins/39/test_photo.jpg
            if 's3.amazonaws.com' in photo_url:
                # Handle both path-style and virtual-hosted-style URLs
                if '/circles-media-259c/' in photo_url:
                    # Path-style: https://s3.amazonaws.com/circles-media-259c/checkins/39/test_photo.jpg
                    s3_key = photo_url.split('/circles-media-259c/')[1]
                else:
                    # Virtual-hosted-style: https://circles-media-259c.s3.amazonaws.com/checkins/39/test_photo.jpg
                    s3_key = photo_url.split('.s3.amazonaws.com/')[1]

                return StorageService.generate_signed_url(s3_key)
            else:
                # Fallback for other S3 URLs
                return photo_url
        except Exception as e:
            # Fallback to original URL if signing fails
            return photo_url
    else:
        # Already a full URL (e.g., from FSQ or local storage)
        return photo_url


@router.post("/search", response_model=list[PublicUserSearchResponse])
async def search_users(
    filters: UserSearchFilters,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Subquery to mark if current_user follows a given user
    followed_subq = (
        select(Follow.followee_id)
        .where(Follow.follower_id == current_user.id)
        .subquery()
    )

    stmt = (
        select(
            User,
            case((followed_subq.c.followee_id.is_not(None), True),
                 else_=False).label("followed"),
        )
        .outerjoin(followed_subq, User.id == followed_subq.c.followee_id)
    )
    blocked_subq = (
        select(DMParticipantState.id)
        .join(DMThread, DMThread.id == DMParticipantState.thread_id)
        .where(
            DMParticipantState.blocked.is_(True),
            or_(
                and_(DMThread.user_a_id == current_user.id,
                     DMThread.user_b_id == User.id),
                and_(DMThread.user_b_id == current_user.id,
                     DMThread.user_a_id == User.id),
            ),
        )
    )
    stmt = stmt.where(~blocked_subq.exists())
    if filters.q:
        like = f"%{filters.q}%"
        stmt = stmt.where(
            User.name.ilike(like) |
            User.username.ilike(like) |
            User.bio.ilike(like)
        )
    if filters.has_avatar is not None:
        if filters.has_avatar:
            stmt = stmt.where(User.avatar_url.is_not(None))
        else:
            stmt = stmt.where(User.avatar_url.is_(None))
    if filters.interests:
        from ..models import UserInterest
        subq = (
            select(UserInterest.user_id)
            .where(UserInterest.name.in_(filters.interests))
            .group_by(UserInterest.user_id)
            .subquery()
        )
        stmt = stmt.where(User.id.in_(select(subq.c.user_id)))
    stmt = stmt.offset(filters.offset).limit(filters.limit)

    res = await db.execute(stmt)
    items = []
    for user, followed in res.all():
        # Check directional blocking - if the target user has blocked current user, skip them
        if await has_user_blocked(db, user.id, current_user.id):
            continue  # Skip users who have blocked the current user

        # Check if user should appear in search results
        if not await should_appear_in_search(db, user, current_user.id):
            continue  # Skip users who don't want to appear in search

        # Check if current user has blocked this user
        is_blocked = await has_user_blocked(db, current_user.id, user.id)

        items.append(
            PublicUserSearchResponse(
                id=user.id,
                name=user.name,
                bio=user.bio,
                avatar_url=_convert_single_to_signed_url(user.avatar_url),
                created_at=user.created_at,
                username=user.username,
                availability_status=user.availability_status,
                availability_mode=getattr(
                    user, "availability_mode", AvailabilityMode.auto.value),
                followed=bool(followed),
                is_blocked=is_blocked,
            )
        )
    return items


@router.get("/{user_id}", response_model=PublicUserResponse)
async def get_user_profile(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    # Add logging for debugging
    import logging
    logging.info(f"Getting user profile for user_id: {user_id}")

    try:
        res = await db.execute(select(User).where(User.id == user_id))
        user = res.scalars().first()

        if not user:
            logging.warning(f"User with ID {user_id} not found in database")
            raise HTTPException(status_code=404, detail="User not found")

        logging.info(f"Found user: {user.id}, name: {user.name}")

        # Check for directional blocks only if there's a current user and it's not the same user
        if current_user and current_user.id != user.id:
            logging.info(
                f"Checking if target user {user.id} has blocked current_user {current_user.id}")
            # If the target user has blocked the current user, return 404
            if await has_user_blocked(db, user.id, current_user.id):
                logging.warning(
                    f"User {user.id} has blocked current_user {current_user.id}")
                raise HTTPException(status_code=404, detail="User not found")

        # Check profile privacy
        if current_user:
            if not await can_view_profile(db, user, current_user.id):
                logging.warning(
                    f"User {current_user.id} cannot view profile of user {user.id} due to privacy settings")
                raise HTTPException(status_code=404, detail="User not found")
        else:
            # Anonymous access - only public profiles
            profile_visibility = getattr(user, 'profile_visibility', 'public')
            if profile_visibility != 'public':
                logging.warning(
                    f"Anonymous user cannot view private profile of user {user.id}")
                raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in get_user_profile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Check if viewer can see stats
    can_see_stats = True
    if current_user:
        can_see_stats = await can_view_stats(db, user, current_user.id)
    else:
        # Anonymous access - only if stats are public
        stats_visibility = getattr(user, 'stats_visibility', 'public')
        can_see_stats = (stats_visibility == 'public')

    # Get counts only if allowed to see stats
    if can_see_stats:
        followers_count = await db.scalar(
            select(func.count()).where(Follow.followee_id == user.id)
        )
        following_count = await db.scalar(
            select(func.count()).where(Follow.follower_id == user.id)
        )
        check_ins_count = await db.scalar(
            select(func.count()).where(CheckIn.user_id == user.id)
        )
    else:
        followers_count = None
        following_count = None
        check_ins_count = None

    # Check if current user is following this user and if current user has blocked this user
    is_followed = None
    is_blocked = None
    if current_user:
        is_followed_result = await db.scalar(
            select(func.count()).where(
                Follow.follower_id == current_user.id,
                Follow.followee_id == user.id
            )
        )
        is_followed = is_followed_result > 0

        # Check if current user has blocked the target user
        if current_user.id != user.id:
            is_blocked = await has_user_blocked(db, current_user.id, user.id)

    return PublicUserResponse(
        id=user.id,
        name=user.name,
        username=user.username,
        bio=user.bio,
        avatar_url=_convert_single_to_signed_url(user.avatar_url),
        availability_status=user.availability_status,
        availability_mode=getattr(
            user, "availability_mode", AvailabilityMode.auto.value),
        created_at=user.created_at,
        followers_count=followers_count,
        following_count=following_count,
        check_ins_count=check_ins_count,
        is_followed=is_followed,
        is_blocked=is_blocked,
    )


@router.put("/me", response_model=PublicUserResponse)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import logging
    logging.info(
        f"User {current_user.id} updating profile: name={payload.name}, bio={payload.bio}")

    # Check if user is verified
    if not current_user.is_verified:
        logging.warning(
            f"User {current_user.id} is not verified, blocking profile update")
        raise HTTPException(
            status_code=403, detail="Account must be verified to update profile")

    try:
        if payload.name is not None:
            current_user.name = payload.name
            logging.info(f"Updated name to: {payload.name}")
        if payload.bio is not None:
            current_user.bio = payload.bio
            logging.info(f"Updated bio to: {payload.bio}")
        if payload.availability_status is not None:
            if payload.availability_status == AvailabilityStatus.not_available:
                current_user.availability_status = AvailabilityStatus.not_available.value
                current_user.availability_mode = AvailabilityMode.manual.value
            else:
                current_user.availability_mode = AvailabilityMode.auto.value
                is_online = manager.is_user_online(current_user.id)
                current_user.availability_status = (
                    AvailabilityStatus.available.value
                    if is_online
                    else AvailabilityStatus.not_available.value
                )

        await db.commit()
        logging.info(
            f"Successfully committed changes for user {current_user.id}")
        await db.refresh(current_user)
        logging.info(f"Successfully refreshed user {current_user.id}")

        # Return proper PublicUserResponse format
        return PublicUserResponse(
            id=current_user.id,
            name=current_user.name,
            username=current_user.username,
            bio=current_user.bio,
            avatar_url=_convert_single_to_signed_url(current_user.avatar_url),
            availability_status=current_user.availability_status,
            availability_mode=getattr(
                current_user, "availability_mode", AvailabilityMode.auto.value),
            created_at=current_user.created_at,
            followers_count=None,  # Not needed for self update
            following_count=None,  # Not needed for self update
            check_ins_count=None,  # Not needed for self update
            is_followed=None,      # Not applicable for self
        )
    except Exception as e:
        logging.error(f"Error updating user {current_user.id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to update profile: {str(e)}")


@router.post("/me/avatar", response_model=PublicUserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import os
    from uuid import uuid4
    # image validation comes from storage service helpers

    # Skip content type validation - let storage service handle image validation

    # Check file size (configurable max MB for avatars)
    from ..config import settings
    max_size = int(settings.avatar_max_mb) * 1024 * 1024

    # Read file in chunks to avoid memory issues
    content = b""
    chunk_size = 64 * 1024  # 64KB chunks
    total_size = 0

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        content += chunk
        total_size += len(chunk)

        # Check size during streaming
        if total_size > max_size:
            raise HTTPException(
                status_code=400,
                detail="Avatar file size must be less than 5MB"
            )

    # Validate image content
    try:
        _validate_image_or_raise(file.filename or "avatar.jpg", content)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    # Generate filename - preserve original extension or use .bin for unknown types
    _, ext = os.path.splitext(file.filename or "")
    if not ext:
        ext = ".bin"  # Generic extension for unknown file types
    filename = f"{uuid4().hex}{ext}"

    # Store avatar using configured storage backend (avatars path)
    url_path = await StorageService.save_avatar(current_user.id, filename, content)

    # Update user avatar
    current_user.avatar_url = url_path
    await db.commit()
    await db.refresh(current_user)

    # Convert to final URL for response (sign S3 keys)
    if settings.storage_backend == "s3" and current_user.avatar_url and not str(current_user.avatar_url).startswith("http"):
        try:
            current_user.avatar_url = StorageService.generate_signed_url(
                current_user.avatar_url)
        except Exception:
            # Fallback: leave S3 key if signing fails
            pass

    return current_user


@router.get("/{user_id}/check-ins", response_model=PaginatedCheckIns)
async def list_user_checkins(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    import logging
    logging.info(
        f"Fetching check-ins for user {user_id}, limit={limit}, offset={offset}")

    # visibility enforcement: reuse can_view_checkin-like logic
    from ..utils import can_view_checkin

    # Get all check-ins for this user to check visibility
    all_checkins_res = await db.execute(
        select(CheckIn)
        .where(CheckIn.user_id == user_id)
        .order_by(CheckIn.created_at.desc())
    )
    all_checkins = all_checkins_res.scalars().all()

    # Filter by visibility and count visible ones
    visible_checkins = []
    for ci in all_checkins:
        if await can_view_checkin(db, ci.user_id, current_user.id, ci.visibility):
            visible_checkins.append(ci)

    # Calculate total visible count
    total_visible = len(visible_checkins)

    # Apply pagination to visible check-ins
    start_idx = offset
    end_idx = offset + limit
    visible = visible_checkins[start_idx:end_idx]
    # hydrate photo_urls
    result: list[CheckInResponse] = []
    from ..config import settings as app_settings
    for ci in visible:
        res_ph = await db.execute(select(CheckInPhoto).where(CheckInPhoto.check_in_id == ci.id).order_by(CheckInPhoto.created_at.asc()))
        urls = [p.url for p in res_ph.scalars().all()]
        # Convert S3 keys to signed URLs
        urls = _convert_to_signed_urls(urls)

        allowed = (datetime.now(timezone.utc) -
                   ci.created_at) <= timedelta(hours=app_settings.place_chat_window_hours)
        result.append(
            CheckInResponse(
                id=ci.id,
                user_id=ci.user_id,
                place_id=ci.place_id,
                note=ci.note,
                visibility=ci.visibility,
                created_at=ci.created_at,
                expires_at=ci.expires_at,
                photo_url=_convert_single_to_signed_url(ci.photo_url),
                photo_urls=urls,
                allowed_to_chat=allowed,
            )
        )
    return PaginatedCheckIns(items=result, total=total_visible, limit=limit, offset=offset)


@router.get("/{user_id}/media", response_model=PaginatedMedia)
async def list_user_media(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    import logging
    logging.info(
        f"Fetching media for user {user_id}, limit={limit}, offset={offset}")

    # collect review photos and check-in photos with visibility checks
    from ..utils import can_view_checkin
    # review photos: always public for now (attached to reviews)
    total_photos = (await db.execute(select(func.count(Photo.id)).where(Photo.user_id == user_id, Photo.review_id.is_not(None)))).scalar_one()
    res_photos = await db.execute(
        select(Photo.url).where(Photo.user_id == user_id, Photo.review_id.is_not(
            None)).order_by(Photo.created_at.desc()).offset(offset).limit(limit)
    )
    urls = [u[0] for u in res_photos.all()]
    # check-in photos: filter via check-in visibility
    res_ci = await db.execute(
        select(CheckIn.id, CheckIn.visibility).where(CheckIn.user_id == user_id).order_by(
            CheckIn.created_at.desc()).offset(0).limit(limit * 3)
    )
    ci_rows = res_ci.all()
    ci_ids = [row[0] for row in ci_rows]
    if ci_ids:
        res_cips = await db.execute(select(CheckInPhoto).where(CheckInPhoto.check_in_id.in_(ci_ids)).order_by(CheckInPhoto.created_at.desc()))
        cip_list = res_cips.scalars().all()
        # map check_in_id -> visibility
        vis_map = {row[0]: row[1] for row in ci_rows}
        for cip in cip_list:
            vis = vis_map.get(cip.check_in_id, "public")
            if await can_view_checkin(db, user_id, current_user.id, vis):
                urls.append(cip.url)
                if len(urls) >= limit:
                    break
    total = total_photos  # approximate; not counting CI photos separately here
    # Convert any S3 keys to signed URLs before returning
    urls = _convert_to_signed_urls(urls)
    items = urls[:limit]
    return PaginatedMedia(items=items, total=total, limit=limit, offset=offset)


@router.get("/{user_id}/collections", response_model=list[dict])
async def list_user_collections(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get user's collections with random photos.

    Returns collections of saved places, each with up to 4 random photos
    from the places in that collection.
    """
    import logging
    logging.info(f"Fetching collections for user {user_id}")

    # Check if the user exists
    try:
        user_res = await db.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
        if not user:
            logging.warning(
                f"User {user_id} not found for collections request")
            raise HTTPException(status_code=404, detail="User not found")
        logging.info(f"Found user {user_id} for collections request")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error checking user {user_id} for collections: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Get collection names and place IDs
    collections_query = (
        select(
            SavedPlace.list_name,
            func.count(SavedPlace.id).label('count'),
            func.array_agg(SavedPlace.place_id).label('place_ids')
        )
        .where(SavedPlace.user_id == user_id)
        .group_by(SavedPlace.list_name)
        .order_by(SavedPlace.list_name.asc())
    )

    result = await db.execute(collections_query)
    collections_data = result.all()
    logging.info(
        f"Found {len(collections_data)} collections for user {user_id}")

    collections = []
    for collection_name, count, place_ids in collections_data:
        # Get up to 4 random photos from places in this collection
        if place_ids and len(place_ids) > 0:
            photos_query = (
                select(Photo.url)
                .where(Photo.place_id.in_(place_ids))
                .order_by(func.random())
                .limit(4)
            )
            photos_result = await db.execute(photos_query)
            photo_urls = photos_result.scalars().all()
            # Convert to signed URLs
            photos = _convert_to_signed_urls(list(photo_urls))
        else:
            photos = []

        collections.append({
            "name": collection_name or "Favorites",
            "count": count,
            "photos": photos
        })

    logging.info(
        f"Returning {len(collections)} collections for user {user_id}")
    return collections


@router.get("/collections/{collection_name}/items", response_model=list[dict])
async def get_collection_items(
    collection_name: str,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get items in a specific saved place collection.

    Returns the places in the specified collection with their photos and details.
    """
    # Get all places in this collection for the current user
    places_query = (
        select(
            SavedPlace,
            Place.name,
            Place.address,
            Place.city,
            Place.latitude,
            Place.longitude,
            Place.rating,
            Place.description,
            Place.categories
        )
        .join(Place, SavedPlace.place_id == Place.id)
        .where(
            SavedPlace.user_id == current_user.id,
            SavedPlace.list_name == collection_name
        )
        .order_by(SavedPlace.created_at.desc())
    )

    result = await db.execute(places_query)
    items = result.all()

    collection_items = []
    for saved_place, place_name, address, city, latitude, longitude, rating, description, categories in items:
        # Get photos for this place
        photos_query = (
            select(Photo.url)
            .where(Photo.place_id == saved_place.place_id)
            .order_by(Photo.created_at.desc())
            .limit(10)  # Limit to prevent too many photos
        )
        photos_result = await db.execute(photos_query)
        photo_urls = photos_result.scalars().all()
        photos = _convert_to_signed_urls(list(photo_urls))

        collection_items.append({
            "saved_place_id": saved_place.id,
            "place_id": saved_place.place_id,
            "place_name": place_name,
            "address": address,
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "rating": rating,
            "description": description,
            "categories": categories,
            "photos": photos,
            "saved_at": saved_place.created_at
        })

    return collection_items


@router.get("/me/interests", response_model=list[InterestResponse])
async def my_interests(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(UserInterest).where(UserInterest.user_id == current_user.id).order_by(UserInterest.created_at.desc()))
    return res.scalars().all()


@router.post("/me/interests", response_model=InterestResponse)
async def add_interest(
    payload: InterestCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # simple upsert avoid dupes
    exists = await db.execute(select(UserInterest).where(UserInterest.user_id == current_user.id, UserInterest.name == payload.name))
    if exists.scalars().first():
        raise HTTPException(status_code=400, detail="Interest already exists")
    it = UserInterest(user_id=current_user.id, name=payload.name)
    db.add(it)
    await db.commit()
    await db.refresh(it)
    return it


@router.delete("/me/interests/{interest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_interest(
    interest_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(UserInterest).where(UserInterest.id == interest_id, UserInterest.user_id == current_user.id))
    it = res.scalars().first()
    if not it:
        raise HTTPException(status_code=404, detail="Interest not found")
    await db.delete(it)
    await db.commit()
    return None


@router.get("/{user_id}/profile-stats", response_model=ProfileStats)
async def get_user_profile_stats(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive profile statistics for a user"""

    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if current user can view this user's stats
    can_view = await can_view_stats(db, user, current_user.id)

    # Get check-in counts by visibility
    checkin_stats = await db.execute(
        select(
            func.count(CheckIn.id).label('total'),
            func.sum(case((CheckIn.visibility == 'public', 1), else_=0)).label(
                'public'),
            func.sum(case((CheckIn.visibility == 'friends', 1), else_=0)).label(
                'followers'),
            func.sum(case((CheckIn.visibility == 'private', 1), else_=0)).label(
                'private')
        ).where(CheckIn.user_id == user_id)
    )
    checkin_row = checkin_stats.fetchone()

    # Get saved place collection counts
    saved_collection_stats = await db.execute(
        select(
            func.count(func.distinct(SavedPlace.list_name)).label('total'),
            func.count(SavedPlace.id).label('total_saved_places')
        ).where(SavedPlace.user_id == user_id)
    )
    saved_collection_row = saved_collection_stats.fetchone()

    # Get follower/following counts
    followers_count = await db.scalar(
        select(func.count(Follow.id)).where(Follow.followee_id == user_id)
    )
    following_count = await db.scalar(
        select(func.count(Follow.id)).where(Follow.follower_id == user_id)
    )

    # Get review and photo counts
    reviews_count = await db.scalar(
        select(func.count(Review.id)).where(Review.user_id == user_id)
    )
    photos_count = await db.scalar(
        select(func.count(Photo.id)).join(Review, Photo.review_id ==
                                          Review.id).where(Review.user_id == user_id)
    )

    # Get total likes and comments received (only if user can view)
    total_likes_received = 0
    total_comments_received = 0

    if can_view:
        total_likes_received = await db.scalar(
            select(func.count(CheckInLike.id))
            .join(CheckIn, CheckInLike.check_in_id == CheckIn.id)
            .where(CheckIn.user_id == user_id)
        )
        total_comments_received = await db.scalar(
            select(func.count(CheckInComment.id))
            .join(CheckIn, CheckInComment.check_in_id == CheckIn.id)
            .where(CheckIn.user_id == user_id)
        )

    return ProfileStats(
        checkins_count=checkin_row.total or 0,
        checkins_public_count=checkin_row.public or 0,
        checkins_followers_count=checkin_row.followers or 0,
        checkins_private_count=checkin_row.private or 0,
        collections_count=saved_collection_row.total or 0,
        collections_public_count=0,  # Saved places don't have visibility for now
        collections_followers_count=0,
        collections_private_count=0,
        followers_count=followers_count or 0,
        following_count=following_count or 0,
        reviews_count=reviews_count or 0,
        photos_count=photos_count or 0,
        total_likes_received=total_likes_received or 0,
        total_comments_received=total_comments_received or 0,
    )


@router.get("/{user_id}/random-place-photos", response_model=list[str])
async def get_random_place_photos(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(4, ge=1, le=4, description="Max 4 random photos"),
    collection: str | None = Query(
        None, description="Saved places collection (list_name) to filter by")
):
    """Return up to 4 random photos from places the user saved.

    - Filters by saved places; if `collection` (list_name) is provided, restricts to that saved collection.
    - Photos come from the `photos` table (place-scoped images), not check-ins.
    """
    base = select(SavedPlace.place_id).where(SavedPlace.user_id == user_id)
    if collection:
        base = base.where(SavedPlace.list_name == collection)

    res = await db.execute(base)
    place_ids = [pid for (pid,) in res.all()]

    if not place_ids:
        return []

    photos_res = await db.execute(
        select(Photo.url)
        .where(Photo.place_id.in_(place_ids))
        .order_by(func.random())
        .limit(limit)
    )
    urls = [row[0] for row in photos_res.all()]
    return _convert_to_signed_urls(urls)


# Removed the separate collection endpoint; use collection_id query param on /random-place-photos
