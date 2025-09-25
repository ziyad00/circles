from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Query
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_, or_, desc

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
    """
    Search for users with various filters.

    **Authentication Required:** Yes
    """
    try:
        # Build base query
        query = select(User).where(
            User.id != current_user.id)  # Exclude current user

        # Apply search filters
        if filters.q:
            query = query.where(
                or_(
                    User.username.ilike(f"%{filters.q}%"),
                    User.display_name.ilike(f"%{filters.q}%"),
                    User.bio.ilike(f"%{filters.q}%")
                )
            )

        # Apply privacy filters
        query = query.where(should_appear_in_search(current_user, User))

        # Apply pagination
        query = query.offset(filters.offset).limit(filters.limit)

        result = await db.execute(query)
        users = result.scalars().all()

        # Convert to response format
        user_responses = []
        for user in users:
            # Check if current user can view this user's profile
            if can_view_profile(current_user, user):
                user_resp = PublicUserSearchResponse(
                    id=user.id,
                    username=user.username,
                    display_name=user.display_name,
                    bio=user.bio,
                    avatar_url=user.avatar_url,
                    is_verified=user.is_verified,
                    followers_count=user.followers_count,
                    following_count=user.following_count,
                    checkins_count=user.checkins_count,
                    is_following=False,  # TODO: Check if current user follows this user
                    mutual_followers_count=0,  # TODO: Calculate mutual followers
                )
                user_responses.append(user_resp)

        return user_responses

    except Exception as e:
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

        # Check if current user can view this profile
        if not can_view_profile(current_user, user):
            raise HTTPException(
                status_code=403, detail="Cannot view this profile")

        # Check if current user follows this user
        follow_query = select(Follow).where(
            and_(
                Follow.follower_id == current_user.id,
                Follow.following_id == user_id
            )
        )
        follow_result = await db.execute(follow_query)
        is_following = follow_result.scalar_one_or_none() is not None

        # Create response
        user_response = PublicUserResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            bio=user.bio,
            avatar_url=user.avatar_url,
            is_verified=user.is_verified,
            followers_count=user.followers_count,
            following_count=user.following_count,
            checkins_count=user.checkins_count,
            is_following=is_following,
            created_at=user.created_at,
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

        # Return updated profile
        return PublicUserResponse(
            id=current_user.id,
            username=current_user.username,
            display_name=current_user.display_name,
            bio=current_user.bio,
            avatar_url=current_user.avatar_url,
            is_verified=current_user.is_verified,
            followers_count=current_user.followers_count,
            following_count=current_user.following_count,
            checkins_count=current_user.checkins_count,
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
        # Validate image
        _validate_image_or_raise(file)

        # Upload to storage
        storage_service = StorageService()
        avatar_url = await storage_service.upload_photo(file, f"avatars/{current_user.id}")

        if not avatar_url:
            raise HTTPException(
                status_code=500, detail="Failed to upload avatar")

        # Update user avatar
        current_user.avatar_url = avatar_url
        current_user.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(current_user)

        # Return updated profile
        return PublicUserResponse(
            id=current_user.id,
            username=current_user.username,
            display_name=current_user.display_name,
            bio=current_user.bio,
            avatar_url=current_user.avatar_url,
            availability_status=current_user.availability_status,
            availability_mode=current_user.availability_mode,
            created_at=current_user.created_at,
            followers_count=current_user.followers_count,
            following_count=current_user.following_count,
            check_in_count=current_user.check_in_count,
        )

    except HTTPException:
        raise
    except Exception as e:
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
        media_items = result.fetchall()

        # Convert to expected format
        items = []
        for item in media_items:
            if item.url:  # Only include items with actual photos
                media_item = {
                    "photo_url": item.url,
                    "created_at": item.created_at,
                    "place_id": item.place_id,
                }
                items.append(media_item)

        return PaginatedMedia(items=items, total=total, limit=limit, offset=offset)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to get user media")


@router.get("/{user_id}/check-ins", response_model=list[dict])
async def get_user_checkins(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
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

        # Get check-ins with place info
        checkins_query = select(
            CheckIn.id,
            CheckIn.place_id,
            CheckIn.note,
            CheckIn.visibility,
            CheckIn.created_at,
            CheckIn.latitude,
            CheckIn.longitude,
            Place.name.label('place_name'),
            Place.address.label('place_address')
        ).join(Place, CheckIn.place_id == Place.id).where(
            CheckIn.user_id == user_id
        ).order_by(desc(CheckIn.created_at)).offset(offset).limit(limit)

        result = await db.execute(checkins_query)
        checkins = result.fetchall()

        # Convert to response format
        checkin_list = []
        for checkin in checkins:
            checkin_dict = {
                "id": checkin.id,
                "place_id": checkin.place_id,
                "place_name": checkin.place_name,
                "place_address": checkin.place_address,
                "note": checkin.note,
                "visibility": checkin.visibility,
                "created_at": checkin.created_at,
                "latitude": checkin.latitude,
                "longitude": checkin.longitude,
            }
            checkin_list.append(checkin_dict)

        return checkin_list

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to get user check-ins")

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

        # Check if current user can view this user's collections
        if not await can_view_profile(db, user, current_user.id):
            raise HTTPException(
                status_code=403, detail="Cannot view this user's collections")

        # Get collections from UserCollection table
        collections_query = select(UserCollection).where(
            UserCollection.user_id == user_id
        ).order_by(UserCollection.name)

        result = await db.execute(collections_query)
        collections = result.scalars().all()

        # Convert to response format with actual data
        collection_list = []
        for collection in collections:
            # Get place count for this collection
            count_query = select(func.count()).select_from(
                select(UserCollectionPlace).where(
                    UserCollectionPlace.collection_id == collection.id
                ).subquery()
            )
            count_result = await db.execute(count_query)
            place_count = count_result.scalar() or 0

            # Get sample photos from places in this collection
            photos_query = select(CheckInPhoto.url).join(
                CheckIn, CheckIn.id == CheckInPhoto.check_in_id
            ).join(
                UserCollectionPlace, UserCollectionPlace.place_id == CheckIn.place_id
            ).where(
                and_(
                    UserCollectionPlace.collection_id == collection.id,
                    CheckInPhoto.url.isnot(None)
                )
            ).limit(3)

            photos_result = await db.execute(photos_query)
            photo_urls = [row[0] for row in photos_result.fetchall()]

            collection_dict = {
                "id": collection.id,
                "name": collection.name,
                "count": place_count,
                "photos": photo_urls
            }
            collection_list.append(collection_dict)

        return collection_list

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to get user collections")
