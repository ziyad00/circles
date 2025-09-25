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

# ============================================================================
# USER SEARCH ENDPOINT (Used by frontend)
# ============================================================================


@router.post("/search", response_model=list[PublicUserSearchResponse])
async def search_users(
    filters: UserSearchFilters,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
        if not can_view_profile(current_user, user):
            raise HTTPException(
                status_code=403, detail="Cannot view this user's media")

        # Get photos from check-ins
        checkin_photos_query = select(CheckInPhoto).join(CheckIn).where(
            and_(
                CheckIn.user_id == user_id,
                CheckInPhoto.photo_url.isnot(None)
            )
        ).order_by(desc(CheckInPhoto.created_at))

        # Get photos from saved places
        saved_place_photos_query = select(Photo).join(SavedPlace).where(
            and_(
                SavedPlace.user_id == user_id,
                Photo.photo_url.isnot(None)
            )
        ).order_by(desc(Photo.created_at))

        # Combine queries using UNION
        from sqlalchemy import union_all

        # Create a unified query structure
        checkin_subquery = select(
            CheckInPhoto.photo_url.label('photo_url'),
            CheckInPhoto.created_at.label('created_at'),
            CheckIn.place_id.label('place_id')
        ).join(CheckIn).where(
            and_(
                CheckIn.user_id == user_id,
                CheckInPhoto.photo_url.isnot(None)
            )
        )

        saved_subquery = select(
            Photo.photo_url.label('photo_url'),
            Photo.created_at.label('created_at'),
            SavedPlace.place_id.label('place_id')
        ).join(SavedPlace).where(
            and_(
                SavedPlace.user_id == user_id,
                Photo.photo_url.isnot(None)
            )
        )

        # Union the queries
        union_query = union_all(
            checkin_subquery, saved_subquery).order_by(desc('created_at'))

        # Get total count
        count_query = select(func.count()).select_from(union_query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        paginated_query = union_query.offset(offset).limit(limit)
        result = await db.execute(paginated_query)
        media_items = result.fetchall()

        # Convert to response format
        items = []
        for item in media_items:
            media_item = {
                "photo_url": item.photo_url,
                "created_at": item.created_at,
                "place_id": item.place_id,
            }
            items.append(media_item)

        return PaginatedMedia(items=items, total=total, limit=limit, offset=offset)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get user media")

# ============================================================================
# USER COLLECTIONS ENDPOINTS (Used by frontend)
# ============================================================================


@router.get("/{user_id}/collections", response_model=list[dict])
async def list_user_collections(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
        if not can_view_profile(current_user, user):
            raise HTTPException(
                status_code=403, detail="Cannot view this user's collections")

        # Get collections with place counts
        collections_query = select(
            SavedPlace.collection_name,
            func.count(SavedPlace.place_id).label('count'),
            func.array_agg(SavedPlace.place_id).label('place_ids')
        ).where(
            SavedPlace.user_id == user_id
        ).group_by(SavedPlace.collection_name).order_by(SavedPlace.collection_name)

        result = await db.execute(collections_query)
        collections = result.fetchall()

        # Convert to response format
        collection_list = []
        for collection in collections:
            collection_dict = {
                "id": None,  # Legacy collections don't have IDs
                "name": collection.collection_name,
                "count": collection.count,
                "photos": []  # TODO: Get sample photos from places
            }
            collection_list.append(collection_dict)

        return collection_list

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="Failed to get user collections")
