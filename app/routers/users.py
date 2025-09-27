import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc

from ..database import get_db
from ..services.jwt_service import JWTService
from ..services.storage import StorageService
from ..services.collection_sync import ensure_default_collection
from ..utils import (
    can_view_checkin,
    can_view_profile,
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
    UserCollection,
    UserCollectionPlace,
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
from ..config import settings
from ..exceptions import ImageTooLargeError

logger = logging.getLogger(__name__)


def _convert_to_signed_urls(photo_urls: list[str]) -> list[str]:
    """Convert storage keys to signed URLs when required."""
    signed_urls: list[str] = []
    for url in photo_urls:
        if url and not url.startswith("http"):
            if settings.storage_backend == "local":
                signed_urls.append(f"http://localhost:8000{url}")
            else:
                try:
                    signed_urls.append(StorageService.generate_signed_url(url))
                except Exception as exc:  # pragma: no cover - fallback path
                    logger.warning("Failed to sign photo URL %s: %s", url, exc)
                signed_urls.append(url)
        elif url:
            signed_urls.append(url)
    return signed_urls


def _convert_single_to_signed_url(photo_url: str | None) -> str | None:
    """Convert a single storage key or S3 URL to a signed URL."""
    if not photo_url:
        return None

    logger.debug(f"Converting URL: {photo_url}, storage_backend: {settings.storage_backend}")

    if not photo_url.startswith("http"):
        if settings.storage_backend == "local":
            return f"http://localhost:8000{photo_url}"
        try:
            signed_url = StorageService.generate_signed_url(photo_url)
            logger.debug(f"Generated signed URL for key {photo_url}: {signed_url}")
            return signed_url
        except Exception as exc:  # pragma: no cover - fallback path
            logger.warning(
                "Failed to sign single photo URL %s: %s", photo_url, exc)
            return photo_url

    if "s3.amazonaws.com" in photo_url or "circles-media" in photo_url:
        try:
            if "s3.amazonaws.com" in photo_url and "/" in photo_url:
                if "/circles-media" in photo_url:
                    s3_key = photo_url.split(
                        "/circles-media", 1)[1].lstrip("/")
                else:
                    s3_key = photo_url.split(".s3.amazonaws.com/", 1)[1]
            else:
                s3_key = photo_url.split(".amazonaws.com/", 1)[1]

            signed_url = StorageService.generate_signed_url(s3_key)
            logger.debug(f"Re-signed S3 URL {photo_url} -> {signed_url}")
            return signed_url
        except Exception as exc:  # pragma: no cover - fallback path
            logger.warning(
                "Failed to re-sign S3 photo URL %s: %s", photo_url, exc)
            return photo_url

    # Return the original URL if it's already a signed URL or external URL
    return photo_url


def _collect_place_photos(place: Place) -> list[str]:
    photo_candidates: list[str] = []

    primary = _convert_single_to_signed_url(getattr(place, "photo_url", None))
    if primary:
        photo_candidates.append(primary)

    additional = getattr(place, "additional_photos", None)
    if additional:
        try:
            parsed = json.loads(additional) if isinstance(
                additional, str) else additional
            if isinstance(parsed, list):
                photo_candidates.extend(
                    _convert_to_signed_urls(
                        [p for p in parsed if isinstance(p, str)])
                )
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse additional_photos for place %s", place.id)

    seen: set[str] = set()
    unique: list[str] = []
    for url in photo_candidates:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


router = APIRouter(prefix="/users", tags=["users"])

# ============================================================================
# USER SEARCH ENDPOINT (Used by frontend)
# ============================================================================


@router.post("/search", response_model=list[PublicUserSearchResponse])
async def search_users(
    filters: UserSearchFilters,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """Search for users with various filters.

    **Authentication Required:** Yes
    """
    try:
        # Build base query excluding the requester
        query = select(User).where(User.id != current_user.id)

        # Apply text filters
        if filters.q:
            query = query.where(
                or_(
                    User.username.ilike(f"%{filters.q}%"),
                    User.display_name.ilike(f"%{filters.q}%"),
                    User.bio.ilike(f"%{filters.q}%"),
                )
            )

        # Pagination
        query = query.offset(filters.offset).limit(filters.limit)

        result = await db.execute(query)
        users = result.scalars().all()

        responses: list[PublicUserSearchResponse] = []
        for user in users:
            if not await should_appear_in_search(db, user, current_user.id):
                continue

            if await can_view_profile(db, user, current_user.id):
                responses.append(
                    PublicUserSearchResponse(
                        id=user.id,
                        username=user.username,
                        display_name=user.display_name,
                        bio=user.bio,
                        avatar_url=_convert_single_to_signed_url(user.avatar_url),
                        is_verified=user.is_verified,
                        followers_count=user.followers_count,
                        following_count=user.following_count,
                        checkins_count=user.checkins_count,
                        is_following=False,  # TODO: compute follow state
                        mutual_followers_count=0,  # TODO: compute mutual count
                    )
                )

        return responses

    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.error("User search failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to search users")

# ============================================================================
# USER PROFILE ENDPOINTS (Used by frontend)
# ============================================================================


@router.get("/{user_id}", response_model=PublicUserResponse)
async def get_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get public user profile information.

    **Authentication Required:** Yes
    """
    try:
        # Get user
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not await can_view_profile(db, user, current_user.id):
            raise HTTPException(
                status_code=403, detail="Cannot view this profile")

        # Check if current user follows this user
        follow_query = select(Follow).where(
            and_(
                Follow.follower_id == current_user.id,
                Follow.followee_id == user_id
            )
        )
        follow_result = await db.execute(follow_query)
        is_following = follow_result.scalar_one_or_none() is not None

        # Create response
        user_response = PublicUserResponse(
            id=user.id,
            name=user.name,
            username=user.username,
            bio=user.bio,
            avatar_url=_convert_single_to_signed_url(user.avatar_url),
            availability_status=user.availability_status,
            availability_mode=user.availability_mode,
            created_at=user.created_at,
            followers_count=0,  # TODO: Calculate actual count
            following_count=0,  # TODO: Calculate actual count
            check_ins_count=0,  # TODO: Calculate actual count
            is_followed=is_following,
            is_blocked=False,  # TODO: Implement blocking logic
        )

        return user_response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="Failed to get user profile")


@router.put("/me", response_model=PublicUserResponse)
async def update_my_profile(
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Update current user's profile.

    **Authentication Required:** Yes
    """
    try:
        # Update user fields
        if user_update.display_name is not None:
            current_user.display_name = user_update.display_name
        if user_update.bio is not None:
            current_user.bio = user_update.bio
        if user_update.username is not None:
            # Check if username is available
            existing_query = select(User).where(
                and_(
                    User.username == user_update.username,
                    User.id != current_user.id
                )
            )
            existing_result = await db.execute(existing_query)
            existing = existing_result.scalar_one_or_none()

            if existing:
                raise HTTPException(
                    status_code=400, detail="Username already taken")

            current_user.username = user_update.username

        current_user.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(current_user)

        followers_count = await db.scalar(
            select(func.count(Follow.id)).where(
                Follow.followee_id == current_user.id)
        ) or 0
        following_count = await db.scalar(
            select(func.count(Follow.id)).where(
                Follow.follower_id == current_user.id)
        ) or 0
        checkins_count = await db.scalar(
            select(func.count(CheckIn.id)).where(
                CheckIn.user_id == current_user.id)
        ) or 0

        return PublicUserResponse(
            id=current_user.id,
            username=current_user.username,
            display_name=current_user.display_name,
            bio=current_user.bio,
            avatar_url=_convert_single_to_signed_url(current_user.avatar_url),
            is_verified=current_user.is_verified,
            followers_count=followers_count,
            following_count=following_count,
            check_ins_count=checkins_count,
            is_following=False,
            created_at=current_user.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update profile")


@router.post("/me/avatar", response_model=PublicUserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Upload user avatar.

    **Authentication Required:** Yes
    """
    try:
        filename = file.filename or "avatar.jpg"
        content = await file.read()

        if not content:
            raise HTTPException(status_code=400, detail="Avatar file is empty")

        max_bytes = int(settings.avatar_max_mb) * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Avatar file size must be less than {settings.avatar_max_mb}MB",
            )

        # Storage service will perform additional validation
        avatar_url = await StorageService.save_avatar(current_user.id, filename, content)

        if not avatar_url:
            raise HTTPException(
                status_code=500, detail="Failed to upload avatar")

        current_user.avatar_url = avatar_url
        current_user.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(current_user)

        followers_count = await db.scalar(
            select(func.count(Follow.id)).where(
                Follow.followee_id == current_user.id)
        ) or 0
        following_count = await db.scalar(
            select(func.count(Follow.id)).where(
                Follow.follower_id == current_user.id)
        ) or 0
        checkins_count = await db.scalar(
            select(func.count(CheckIn.id)).where(
                CheckIn.user_id == current_user.id)
        ) or 0

        signed_avatar = _convert_single_to_signed_url(current_user.avatar_url)

        return PublicUserResponse(
            id=current_user.id,
            name=current_user.name,
            username=current_user.username,
            bio=current_user.bio,
            avatar_url=signed_avatar,
            availability_status=current_user.availability_status,
            availability_mode=current_user.availability_mode,
            created_at=current_user.created_at,
            followers_count=followers_count,
            following_count=following_count,
            check_ins_count=checkins_count,
            is_followed=None,
            is_blocked=None,
        )

    except ImageTooLargeError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.error("Avatar upload failed: %s", exc)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to upload avatar")

# ============================================================================
# USER MEDIA ENDPOINTS (Used by frontend)
# ============================================================================


@router.get("/{user_id}/media", response_model=PaginatedMedia)
async def get_user_media(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get user's media (photos from check-ins and saved places).

    **Authentication Required:** Yes
    """
    try:
        # Get user
        user_query = select(User).where(User.id == user_id)
        user_result = await db.execute(user_query)
        user = user_result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if current user can view this user's media
        if not await can_view_profile(db, user, current_user.id):
            raise HTTPException(
                status_code=403, detail="Cannot view this user's media")

        # Get total count of check-in photos for this user
        checkin_count_query = select(func.count(CheckInPhoto.id)).join(CheckIn).where(
            and_(
                CheckIn.user_id == user_id,
                CheckInPhoto.url.isnot(None)
            )
        )
        checkin_count_result = await db.execute(checkin_count_query)
        total = checkin_count_result.scalar() or 0

        # Get check-in photos with pagination
        checkin_photos_query = select(
            CheckInPhoto.url,
            CheckInPhoto.created_at,
            CheckIn.place_id
        ).join(CheckIn).where(
            and_(
                CheckIn.user_id == user_id,
                CheckInPhoto.url.isnot(None)
            )
        ).order_by(desc(CheckInPhoto.created_at)).offset(offset).limit(limit)

        result = await db.execute(checkin_photos_query)
        media_items = [row.url for row in result.fetchall() if row.url]

        signed_urls = _convert_to_signed_urls(media_items)

        return PaginatedMedia(
            items=signed_urls,
            total=total,
            limit=limit,
            offset=offset,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to get user media")


@router.get("/{user_id}/check-ins", response_model=PaginatedCheckIns)
async def get_user_checkins(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
) -> PaginatedCheckIns:
    """
    Get user's check-ins.

    **Authentication Required:** Yes
    """
    try:
        # Get user
        user_query = select(User).where(User.id == user_id)
        user_result = await db.execute(user_query)
        user = user_result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if current user can view this user's check-ins
        if not await can_view_profile(db, user, current_user.id):
            raise HTTPException(
                status_code=403, detail="Cannot view this user's check-ins")

        # Fetch all check-ins to enforce visibility rules before pagination
        all_checkins_result = await db.execute(
            select(CheckIn)
            .where(CheckIn.user_id == user_id)
            .order_by(desc(CheckIn.created_at))
        )
        all_checkins = all_checkins_result.scalars().all()

        visible_checkins: list[CheckIn] = []
        for ci in all_checkins:
            if await can_view_checkin(db, ci.user_id, current_user.id, ci.visibility):
                visible_checkins.append(ci)

        total = len(visible_checkins)
        paginated_checkins = visible_checkins[offset: offset + limit]

        if not paginated_checkins:
            return PaginatedCheckIns(items=[], total=total, limit=limit, offset=offset)

        checkin_ids = [ci.id for ci in paginated_checkins]
        photo_rows = await db.execute(
            select(CheckInPhoto.check_in_id, CheckInPhoto.url)
            .where(CheckInPhoto.check_in_id.in_(checkin_ids))
            .order_by(CheckInPhoto.check_in_id, asc(CheckInPhoto.created_at))
        )
        photos_by_checkin: dict[int, list[str]] = {}
        for checkin_id, url in photo_rows.all():
            photos_by_checkin.setdefault(checkin_id, []).append(url)

        place_ids = {ci.place_id for ci in paginated_checkins}
        place_map: dict[int, Place] = {}
        place_photo_map: dict[int, list[str]] = {}
        if place_ids:
            place_rows = await db.execute(
                select(Place).where(Place.id.in_(place_ids))
            )
            for place in place_rows.scalars().all():
                place_map[place.id] = place
                place_photo_map[place.id] = _collect_place_photos(place)

        chat_window = timedelta(hours=settings.place_chat_window_hours)
        now = datetime.now(timezone.utc)

        checkin_responses = []
        for checkin in paginated_checkins:
            raw_photo_urls = photos_by_checkin.get(checkin.id, [])
            signed_photos = _convert_to_signed_urls(raw_photo_urls)

            # Fallback on legacy single photo field if needed
            if not signed_photos and checkin.photo_url:
                single_signed = _convert_single_to_signed_url(
                    checkin.photo_url)
                if single_signed:
                    signed_photos = [single_signed]

            if not signed_photos:
                place_photos = place_photo_map.get(checkin.place_id)
                if place_photos:
                    signed_photos = place_photos[:1]

            if checkin.created_at.tzinfo is None:
                created_at = checkin.created_at.replace(tzinfo=timezone.utc)
            else:
                created_at = checkin.created_at

            allowed_to_chat = (now - created_at) <= chat_window

            photo_url = signed_photos[0] if signed_photos else _convert_single_to_signed_url(
                checkin.photo_url)
            if not photo_url:
                place_photos = place_photo_map.get(checkin.place_id)
                if place_photos:
                    photo_url = place_photos[0]

            checkin_responses.append(
                CheckInResponse(
                    id=checkin.id,
                    user_id=checkin.user_id,
                    place_id=checkin.place_id,
                    note=checkin.note,
                    visibility=checkin.visibility,
                    created_at=checkin.created_at,
                    expires_at=checkin.expires_at,
                    latitude=checkin.latitude,
                    longitude=checkin.longitude,
                    photo_url=photo_url,
                    photo_urls=signed_photos,
                    allowed_to_chat=allowed_to_chat,
                )
            )

        return PaginatedCheckIns(
            items=checkin_responses,
            total=total,
            limit=limit,
            offset=offset,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to get user check-ins")

# ============================================================================
# USER COLLECTIONS ENDPOINTS (Used by frontend)
# ============================================================================


@router.get("/{user_id}/collections", response_model=list[dict])
async def list_user_collections(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get user's collections (saved places grouped by collection name).

    **Authentication Required:** Yes
    """
    try:
        # Check if user exists
        user_query = select(User).where(User.id == user_id)
        user_result = await db.execute(user_query)
        user = user_result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not await can_view_profile(db, user, current_user.id):
            raise HTTPException(
                status_code=403, detail="Cannot view this user's collections")

        await ensure_default_collection(db, user_id)

        collections_stmt = (
            select(
                UserCollection,
                func.count(UserCollectionPlace.id).label("place_count"),
            )
            .outerjoin(
                UserCollectionPlace,
                UserCollectionPlace.collection_id == UserCollection.id,
            )
            .where(UserCollection.user_id == user_id)
            .group_by(UserCollection.id)
            .order_by(UserCollection.name)
            .offset(offset)
            .limit(limit)
        )

        result = await db.execute(collections_stmt)
        rows = result.all()

        collection_list: list[dict] = []
        for collection, place_count in rows:
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
                        CheckIn.user_id == user_id,
                        CheckInPhoto.url.isnot(None),
                    )
                )
                .order_by(desc(CheckInPhoto.created_at))
                .limit(3)
            )

            photos_result = await db.execute(photos_query)
            photo_urls = [row[0] for row in photos_result.fetchall()]
            photo_urls = _convert_to_signed_urls(photo_urls)

            visibility_value = collection.visibility or (
                "public" if collection.is_public else "private"
            )

            collection_list.append(
                {
                    "id": collection.id,
                    "user_id": collection.user_id,
                    "name": collection.name,
                    "description": collection.description,
                    "is_public": collection.is_public,
                    "visibility": visibility_value,
                    "photos": photo_urls,
                    "photo_urls": photo_urls,
                    "place_count": place_count,
                }
            )

        return collection_list

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to get user collections")
