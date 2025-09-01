from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from ..database import get_db
from ..services.jwt_service import JWTService
from ..services.storage import StorageService, _validate_image_or_raise
from ..models import User, CheckIn, CheckInPhoto, Photo, Follow, UserInterest, CheckInCollection, CheckInLike, CheckInComment, Review
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
)


router = APIRouter(prefix="/users", tags=["users"])


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
    if filters.q:
        like = f"%{filters.q}%"
        stmt = stmt.where(User.name.ilike(like) | User.username.ilike(like))
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
        items.append(
            PublicUserSearchResponse(
                id=user.id,
                name=user.name,
                bio=user.bio,
                avatar_url=user.avatar_url,
                created_at=user.created_at,
                username=user.username,
                followed=bool(followed),
            )
        )
    return items


@router.get("/{user_id}", response_model=PublicUserResponse)
async def get_user_profile(user_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    followers_count = await db.scalar(
        select(func.count()).where(Follow.followee_id == user.id)
    )
    following_count = await db.scalar(
        select(func.count()).where(Follow.follower_id == user.id)
    )

    return PublicUserResponse(
        id=user.id,
        name=user.name,
        username=user.username,
        bio=user.bio,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        followers_count=followers_count,
        following_count=following_count,
    )


@router.put("/me", response_model=PublicUserResponse)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.name is not None:
        current_user.name = payload.name
    if payload.bio is not None:
        current_user.bio = payload.bio
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/me/avatar", response_model=PublicUserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import os
    from uuid import uuid4
    # image validation comes from storage service helpers

    # Validate file type and size
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400,
            detail="File must be an image (JPEG, PNG, WebP)"
        )

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
            detail=f"Invalid image file: {str(e)}"
        )

    # Generate filename
    _, ext = os.path.splitext(file.filename or "")
    if not ext:
        ext = ".jpg"
    filename = f"{uuid4().hex}{ext}"

    # Store avatar using configured storage backend
    if settings.storage_backend == "s3":
        # S3 storage
        url_path = await StorageService._save_checkin_s3(current_user.id, filename, content)
    else:
        # Local storage
        media_root = os.path.abspath(os.path.join(os.getcwd(), "media"))
        target_dir = os.path.join(media_root, "avatars", str(current_user.id))
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)

        # Write file synchronously to avoid external dependency issues
        with open(target_path, "wb") as f:
            f.write(content)

        url_path = f"/media/avatars/{current_user.id}/{filename}"

    # Update user avatar
    current_user.avatar_url = url_path
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/{user_id}/check-ins", response_model=PaginatedCheckIns)
async def list_user_checkins(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
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
    for ci in visible:
        res_ph = await db.execute(select(CheckInPhoto).where(CheckInPhoto.check_in_id == ci.id).order_by(CheckInPhoto.created_at.asc()))
        urls = [p.url for p in res_ph.scalars().all()]
        result.append(
            CheckInResponse(
                id=ci.id,
                user_id=ci.user_id,
                place_id=ci.place_id,
                note=ci.note,
                visibility=ci.visibility,
                created_at=ci.created_at,
                expires_at=ci.expires_at,
                photo_url=ci.photo_url,
                photo_urls=urls,
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
    items = urls[:limit]
    return PaginatedMedia(items=items, total=total, limit=limit, offset=offset)


@router.get("/{user_id}/collections", response_model=list[dict])
async def list_user_collections(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Owner gets all; others get public or friends (followers-only)
    base = select(CheckInCollection).where(
        CheckInCollection.user_id == user_id)
    if current_user.id != user_id:
        from ..models import Follow
        is_follower = (await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == user_id))).scalars().first() is not None
        if is_follower:
            base = base.where(
                CheckInCollection.visibility.in_(["public", "friends"]))
        else:
            base = base.where(CheckInCollection.visibility == "public")
    res = await db.execute(base.order_by(CheckInCollection.created_at.desc()))
    cols = res.scalars().all()
    # return minimal fields
    return [{"id": c.id, "name": c.name, "visibility": c.visibility, "created_at": c.created_at} for c in cols]


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

    # Check if current user can view this profile
    # Allow viewing stats if it's own profile or follower; otherwise restrict advanced stats
    can_view = user_id == current_user.id or (
        await db.scalar(
            select(func.count(Follow.id)).where(
                Follow.follower_id == current_user.id,
                Follow.followee_id == user_id,
            )
        )
        > 0
    )

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

    # Get collection counts by visibility
    collection_stats = await db.execute(
        select(
            func.count(CheckInCollection.id).label('total'),
            func.sum(case((CheckInCollection.visibility ==
                     'public', 1), else_=0)).label('public'),
            func.sum(case((CheckInCollection.visibility == 'friends', 1), else_=0)).label(
                'followers'),
            func.sum(case((CheckInCollection.visibility ==
                     'private', 1), else_=0)).label('private')
        ).where(CheckInCollection.user_id == user_id)
    )
    collection_row = collection_stats.fetchone()

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
        collections_count=collection_row.total or 0,
        collections_public_count=collection_row.public or 0,
        collections_followers_count=collection_row.followers or 0,
        collections_private_count=collection_row.private or 0,
        followers_count=followers_count or 0,
        following_count=following_count or 0,
        reviews_count=reviews_count or 0,
        photos_count=photos_count or 0,
        total_likes_received=total_likes_received or 0,
        total_comments_received=total_comments_received or 0,
    )
