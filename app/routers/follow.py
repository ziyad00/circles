from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from ..database import get_db
from ..models import User, Follow
from ..services.jwt_service import JWTService
from ..schemas import PaginatedFollowers, PaginatedFollowing, FollowUserResponse, FollowStatusResponse
from ..routers.activity import create_follow_activity
from ..services.storage import StorageService
from ..utils import can_view_follower_list, can_view_following_list
from ..services.block_service import has_user_blocked


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


router = APIRouter(prefix="/follow", tags=["follow"])


@router.post("/{user_id}", response_model=FollowStatusResponse)
async def follow_user(user_id: int, current_user: User = Depends(JWTService.get_current_user), db: AsyncSession = Depends(get_db)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
    res = await db.execute(select(User).where(User.id == user_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    res = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == user_id))
    if res.scalars().first():
        return {"followed": True}
    db.add(Follow(follower_id=current_user.id, followee_id=user_id))
    await db.commit()

    # Create activity for the follow
    try:
        await create_follow_activity(
            db=db,
            follower_id=current_user.id,
            followee_id=user_id,
            followee_name=target.name or f"User {target.id}"
        )
    except Exception as e:
        # Log error but don't fail the follow creation
        print(
            f"Failed to create activity for follow {current_user.id} -> {user_id}: {e}")

    return {"followed": True}


@router.delete("/{user_id}", response_model=FollowStatusResponse)
async def unfollow_user(user_id: int, current_user: User = Depends(JWTService.get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == user_id))
    row = res.scalars().first()
    if not row:
        return {"followed": False}
    await db.delete(row)
    await db.commit()
    return {"followed": False}


@router.get("/followers", response_model=PaginatedFollowers)
async def list_followers(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), current_user: User = Depends(JWTService.get_current_user), db: AsyncSession = Depends(get_db)):
    # Users who follow current_user
    followers_subq = select(Follow).where(
        Follow.followee_id == current_user.id).subquery()

    # Subquery of users current_user follows (to detect mutual follow)
    my_following_subq = select(Follow.followee_id).where(
        Follow.follower_id == current_user.id).subquery()

    total = (await db.execute(select(func.count()).select_from(followers_subq))).scalar_one()
    res = await db.execute(
        select(
            User,
            followers_subq.c.created_at,
            func.coalesce(func.bool_or(
                my_following_subq.c.followee_id.is_not(None)), False)
        )
        .join_from(User, followers_subq, User.id == followers_subq.c.follower_id)
        .outerjoin(my_following_subq, User.id == my_following_subq.c.followee_id)
        .group_by(User.id, followers_subq.c.created_at)
        .order_by(desc(followers_subq.c.created_at))
        .offset(offset)
        .limit(limit)
    )
    items = []
    for (u, created_at, followed) in res.all():
        # Skip users who have blocked the current user
        if await has_user_blocked(db, u.id, current_user.id):
            continue

        # Check if current user has blocked this user
        is_blocked = await has_user_blocked(db, current_user.id, u.id)

        items.append(
            FollowUserResponse(
                id=u.id,
                username=u.username,
                bio=u.bio,
                avatar_url=_convert_single_to_signed_url(u.avatar_url),
                availability_status=u.availability_status,
                is_verified=u.is_verified,
                created_at=u.created_at,
                followed_at=created_at,
                followed=bool(followed),
                is_blocked=is_blocked
            )
        )
    return PaginatedFollowers(items=items, total=total, limit=limit, offset=offset)


@router.get("/following", response_model=PaginatedFollowing)
async def list_following(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), current_user: User = Depends(JWTService.get_current_user), db: AsyncSession = Depends(get_db)):
    subq = select(Follow).where(
        Follow.follower_id == current_user.id).subquery()
    total = (await db.execute(select(func.count()).select_from(subq))).scalar_one()
    res = await db.execute(
        select(User, subq.c.created_at).join_from(User, subq, User.id == subq.c.followee_id).order_by(
            desc(subq.c.created_at)).offset(offset).limit(limit)
    )
    items = []
    for (u, created_at) in res.all():
        # Skip users who have blocked the current user
        if await has_user_blocked(db, u.id, current_user.id):
            continue

        # Check if current user has blocked this user
        is_blocked = await has_user_blocked(db, current_user.id, u.id)

        items.append(
            FollowUserResponse(
                id=u.id,
                username=u.username,
                bio=u.bio,
                avatar_url=_convert_single_to_signed_url(u.avatar_url),
                availability_status=u.availability_status,
                is_verified=u.is_verified,
                created_at=u.created_at,
                followed_at=created_at,
                followed=True,
                is_blocked=is_blocked
            )
        )
    return PaginatedFollowing(items=items, total=total, limit=limit, offset=offset)


@router.get("/{user_id}/followers", response_model=PaginatedFollowers)
async def list_user_followers(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific user's followers with privacy enforcement."""
    # Get the target user
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if current user can view this user's follower list
    can_view = await can_view_follower_list(db, target_user, current_user.id)
    if not can_view:
        raise HTTPException(status_code=403, detail="Cannot view follower list")

    # Users who follow target_user
    followers_subq = select(Follow).where(
        Follow.followee_id == user_id).subquery()

    # Subquery of users current_user follows (to detect mutual follow)
    my_following_subq = select(Follow.followee_id).where(
        Follow.follower_id == current_user.id).subquery()

    total = (await db.execute(select(func.count()).select_from(followers_subq))).scalar_one()
    res = await db.execute(
        select(
            User,
            followers_subq.c.created_at,
            func.coalesce(func.bool_or(
                my_following_subq.c.followee_id.is_not(None)), False)
        )
        .join_from(User, followers_subq, User.id == followers_subq.c.follower_id)
        .outerjoin(my_following_subq, User.id == my_following_subq.c.followee_id)
        .group_by(User.id, followers_subq.c.created_at)
        .order_by(desc(followers_subq.c.created_at))
        .offset(offset)
        .limit(limit)
    )
    items = [
        FollowUserResponse(
            id=u.id,
            username=u.username,
            bio=u.bio,
            avatar_url=_convert_single_to_signed_url(u.avatar_url),
            availability_status=u.availability_status,
            is_verified=u.is_verified,
            created_at=u.created_at,
            followed_at=created_at,
            followed=bool(followed)
        )
        for (u, created_at, followed) in res.all()
    ]
    return PaginatedFollowers(items=items, total=total, limit=limit, offset=offset)


@router.get("/{user_id}/following", response_model=PaginatedFollowing)
async def list_user_following(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific user's following list with privacy enforcement."""
    # Get the target user
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if current user can view this user's following list
    can_view = await can_view_following_list(db, target_user, current_user.id)
    if not can_view:
        raise HTTPException(status_code=403, detail="Cannot view following list")

    subq = select(Follow).where(
        Follow.follower_id == user_id).subquery()
    total = (await db.execute(select(func.count()).select_from(subq))).scalar_one()
    res = await db.execute(
        select(User, subq.c.created_at).join_from(User, subq, User.id == subq.c.followee_id).order_by(
            desc(subq.c.created_at)).offset(offset).limit(limit)
    )
    items = [
        FollowUserResponse(
            id=u.id,
            username=u.username,
            bio=u.bio,
            avatar_url=_convert_single_to_signed_url(u.avatar_url),
            availability_status=u.availability_status,
            is_verified=u.is_verified,
            created_at=u.created_at,
            followed_at=created_at,
            followed=True
        )
        for (u, created_at) in res.all()
    ]
    return PaginatedFollowing(items=items, total=total, limit=limit, offset=offset)
