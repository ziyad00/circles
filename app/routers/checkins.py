from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import CheckIn, CheckInComment, CheckInLike, User, Place
from ..schemas import (
    CheckInCommentCreate,
    CheckInCommentResponse,
    PaginatedCheckInComments,
    CheckInLikeResponse,
    PaginatedCheckInLikes,
    DetailedCheckInResponse,
    CheckInStats,
)
from ..services.jwt_service import JWTService
from ..utils import can_view_checkin

router = APIRouter(prefix="/check-ins", tags=["check-ins"])


@router.get("/{check_in_id}", response_model=DetailedCheckInResponse)
async def get_check_in_detail(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed check-in information with social stats"""

    # Get check-in with place and user info
    stmt = (
        select(CheckIn)
        .options(
            selectinload(CheckIn.user),
            selectinload(CheckIn.place),
            selectinload(CheckIn.photos),
            selectinload(CheckIn.comments),
            selectinload(CheckIn.likes)
        )
        .where(CheckIn.id == check_in_id)
    )

    result = await db.execute(stmt)
    check_in = result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    # Check visibility
    can_view = await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility)
    if not can_view:
        raise HTTPException(
            status_code=403, detail="You don't have permission to view this check-in")

    # Get social stats
    likes_count = len(check_in.likes)
    comments_count = len(check_in.comments)
    is_liked_by_user = any(
        like.user_id == current_user.id for like in check_in.likes)

    # Get photo URLs
    photo_urls = [photo.url for photo in check_in.photos]

    return DetailedCheckInResponse(
        id=check_in.id,
        user_id=check_in.user_id,
        user_name=check_in.user.name or f"User {check_in.user.id}",
        user_avatar_url=check_in.user.avatar_url,
        place_id=check_in.place_id,
        place_name=check_in.place.name,
        note=check_in.note,
        visibility=check_in.visibility,
        created_at=check_in.created_at,
        expires_at=check_in.expires_at,
        photo_url=check_in.photo_url,
        photo_urls=photo_urls,
        likes_count=likes_count,
        comments_count=comments_count,
        is_liked_by_user=is_liked_by_user,
    )


@router.get("/{check_in_id}/stats", response_model=CheckInStats)
async def get_check_in_stats(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get check-in statistics"""

    # Get check-in
    result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    # Check visibility
    can_view = await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility)
    if not can_view:
        raise HTTPException(
            status_code=403, detail="You don't have permission to view this check-in")

    # Get counts
    likes_count = await db.scalar(
        select(func.count(CheckInLike.id)).where(
            CheckInLike.check_in_id == check_in_id)
    )
    comments_count = await db.scalar(
        select(func.count(CheckInComment.id)).where(
            CheckInComment.check_in_id == check_in_id)
    )
    is_liked_by_user = await db.scalar(
        select(CheckInLike.id).where(
            CheckInLike.check_in_id == check_in_id,
            CheckInLike.user_id == current_user.id
        )
    ) is not None

    return CheckInStats(
        likes_count=likes_count,
        comments_count=comments_count,
        is_liked_by_user=is_liked_by_user,
    )


@router.get("/{check_in_id}/comments", response_model=PaginatedCheckInComments)
async def get_check_in_comments(
    check_in_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get comments for a check-in"""

    # Get check-in
    result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    # Check visibility
    can_view = await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility)
    if not can_view:
        raise HTTPException(
            status_code=403, detail="You don't have permission to view this check-in")

    # Get comments with user info
    stmt = (
        select(CheckInComment)
        .options(selectinload(CheckInComment.user))
        .where(CheckInComment.check_in_id == check_in_id)
        .order_by(CheckInComment.created_at.asc())
        .offset(offset)
        .limit(limit)
    )

    count_stmt = (
        select(func.count(CheckInComment.id))
        .where(CheckInComment.check_in_id == check_in_id)
    )

    total = await db.scalar(count_stmt)
    comments = (await db.execute(stmt)).scalars().all()

    items = [
        CheckInCommentResponse(
            id=comment.id,
            check_in_id=comment.check_in_id,
            user_id=comment.user_id,
            user_name=comment.user.name or f"User {comment.user.id}",
            user_avatar_url=comment.user.avatar_url,
            content=comment.content,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
        )
        for comment in comments
    ]

    return PaginatedCheckInComments(items=items, total=total, limit=limit, offset=offset)


@router.post("/{check_in_id}/comments", response_model=CheckInCommentResponse)
async def add_check_in_comment(
    check_in_id: int,
    comment_data: CheckInCommentCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to a check-in"""

    # Get check-in
    result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    # Check visibility
    can_view = await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility)
    if not can_view:
        raise HTTPException(
            status_code=403, detail="You don't have permission to comment on this check-in")

    # Create comment
    comment = CheckInComment(
        check_in_id=check_in_id,
        user_id=current_user.id,
        content=comment_data.content,
    )

    db.add(comment)
    await db.commit()
    await db.refresh(comment, ['user'])

    return CheckInCommentResponse(
        id=comment.id,
        check_in_id=comment.check_in_id,
        user_id=comment.user_id,
        user_name=comment.user.name or f"User {comment.user.id}",
        user_avatar_url=comment.user.avatar_url,
        content=comment.content,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.delete("/{check_in_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_check_in_comment(
    check_in_id: int,
    comment_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a comment from a check-in"""

    # Get comment
    result = await db.execute(
        select(CheckInComment).where(
            CheckInComment.id == comment_id,
            CheckInComment.check_in_id == check_in_id
        )
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Check ownership
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You can only delete your own comments")

    await db.delete(comment)
    await db.commit()


@router.get("/{check_in_id}/likes", response_model=PaginatedCheckInLikes)
async def get_check_in_likes(
    check_in_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get likes for a check-in"""

    # Get check-in
    result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    # Check visibility
    can_view = await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility)
    if not can_view:
        raise HTTPException(
            status_code=403, detail="You don't have permission to view this check-in")

    # Get likes with user info
    stmt = (
        select(CheckInLike)
        .options(selectinload(CheckInLike.user))
        .where(CheckInLike.check_in_id == check_in_id)
        .order_by(CheckInLike.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    count_stmt = (
        select(func.count(CheckInLike.id))
        .where(CheckInLike.check_in_id == check_in_id)
    )

    total = await db.scalar(count_stmt)
    likes = (await db.execute(stmt)).scalars().all()

    items = [
        CheckInLikeResponse(
            id=like.id,
            check_in_id=like.check_in_id,
            user_id=like.user_id,
            user_name=like.user.name or f"User {like.user.id}",
            user_avatar_url=like.user.avatar_url,
            created_at=like.created_at,
        )
        for like in likes
    ]

    return PaginatedCheckInLikes(items=items, total=total, limit=limit, offset=offset)


@router.post("/{check_in_id}/like", status_code=status.HTTP_200_OK)
async def like_check_in(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Like a check-in"""

    # Get check-in
    result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    # Check visibility
    can_view = await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility)
    if not can_view:
        raise HTTPException(
            status_code=403, detail="You don't have permission to like this check-in")

    # Check if already liked
    existing_like = await db.scalar(
        select(CheckInLike).where(
            CheckInLike.check_in_id == check_in_id,
            CheckInLike.user_id == current_user.id
        )
    )

    if existing_like:
        raise HTTPException(
            status_code=400, detail="You have already liked this check-in")

    # Create like
    like = CheckInLike(
        check_in_id=check_in_id,
        user_id=current_user.id,
    )

    db.add(like)
    await db.commit()

    return {"message": "Check-in liked successfully"}


@router.delete("/{check_in_id}/like", status_code=status.HTTP_200_OK)
async def unlike_check_in(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlike a check-in"""

    # Get like
    result = await db.execute(
        select(CheckInLike).where(
            CheckInLike.check_in_id == check_in_id,
            CheckInLike.user_id == current_user.id
        )
    )
    like = result.scalar_one_or_none()

    if not like:
        raise HTTPException(status_code=404, detail="Like not found")

    await db.delete(like)
    await db.commit()

    return {"message": "Check-in unliked successfully"}
