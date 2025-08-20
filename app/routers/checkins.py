from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta

from ..database import get_db
from ..models import CheckIn, User, Place, CheckInPhoto, CheckInComment, CheckInLike
from ..schemas import (
    DetailedCheckInResponse,
    CheckInCommentCreate,
    CheckInCommentResponse,
    PaginatedCheckInComments,
    CheckInLikeResponse,
    PaginatedCheckInLikes,
    CheckInStats,
)
from ..services.jwt_service import JWTService
from ..utils import can_view_checkin
from ..routers.activity import create_like_activity, create_comment_activity

router = APIRouter(prefix="/check-ins", tags=["check-ins"])


@router.get("/{check_in_id}", response_model=DetailedCheckInResponse)
async def get_check_in_detail(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed check-in information with comments, likes, and photos"""

    # Get check-in with user and place info
    stmt = (
        select(CheckIn)
        .where(CheckIn.id == check_in_id)
        .options(
            selectinload(CheckIn.user),
            selectinload(CheckIn.place),
            selectinload(CheckIn.photos)
        )
    )
    result = await db.execute(stmt)
    check_in = result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    # Check visibility permissions
    if not await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility):
        raise HTTPException(
            status_code=403, detail="Not authorized to view this check-in")

    # Get photo URLs
    photo_urls = [photo.url for photo in check_in.photos]

    # Get likes count
    likes_count_result = await db.execute(
        select(func.count(CheckInLike.id)).where(
            CheckInLike.check_in_id == check_in_id)
    )
    likes_count = likes_count_result.scalar_one()

    # Get comments count
    comments_count_result = await db.execute(
        select(func.count(CheckInComment.id)).where(
            CheckInComment.check_in_id == check_in_id)
    )
    comments_count = comments_count_result.scalar_one()

    # Check if current user liked this check-in
    user_like_result = await db.execute(
        select(CheckInLike.id).where(
            CheckInLike.check_in_id == check_in_id,
            CheckInLike.user_id == current_user.id
        )
    )
    is_liked_by_current_user = user_like_result.scalar_one_or_none() is not None

    # Check permissions
    can_edit = check_in.user_id == current_user.id
    can_delete = check_in.user_id == current_user.id

    return DetailedCheckInResponse(
        id=check_in.id,
        user_id=check_in.user_id,
        user_name=check_in.user.name or check_in.user.email,
        user_avatar_url=check_in.user.avatar_url,
        place_id=check_in.place_id,
        place_name=check_in.place.name,
        place_address=check_in.place.address,
        place_city=check_in.place.city,
        place_neighborhood=check_in.place.neighborhood,
        place_categories=check_in.place.categories,
        place_rating=check_in.place.rating,
        note=check_in.note,
        visibility=check_in.visibility,
        created_at=check_in.created_at,
        updated_at=check_in.created_at,  # CheckIn doesn't have updated_at, using created_at
        photo_urls=photo_urls,
        likes_count=likes_count,
        comments_count=comments_count,
        is_liked_by_current_user=is_liked_by_current_user,
        can_edit=can_edit,
        can_delete=can_delete
    )


@router.get("/{check_in_id}/stats", response_model=CheckInStats)
async def get_check_in_stats(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get check-in statistics (likes, comments, views)"""

    # Verify check-in exists and user can view it
    check_in_result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = check_in_result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    if not can_view_checkin(check_in, current_user):
        raise HTTPException(
            status_code=403, detail="Not authorized to view this check-in")

    # Get counts
    likes_count_result = await db.execute(
        select(func.count(CheckInLike.id)).where(
            CheckInLike.check_in_id == check_in_id)
    )
    likes_count = likes_count_result.scalar_one()

    comments_count_result = await db.execute(
        select(func.count(CheckInComment.id)).where(
            CheckInComment.check_in_id == check_in_id)
    )
    comments_count = comments_count_result.scalar_one()

    # For now, views count is 0 (could be implemented with a separate views table)
    views_count = 0

    return CheckInStats(
        check_in_id=check_in_id,
        likes_count=likes_count,
        comments_count=comments_count,
        views_count=views_count
    )


@router.get("/{check_in_id}/comments", response_model=PaginatedCheckInComments)
async def get_check_in_comments(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get comments for a check-in"""

    # Verify check-in exists and user can view it
    check_in_result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = check_in_result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    if not await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility):
        raise HTTPException(
            status_code=403, detail="Not authorized to view this check-in")

    # Get total count
    total_result = await db.execute(
        select(func.count(CheckInComment.id)).where(
            CheckInComment.check_in_id == check_in_id)
    )
    total = total_result.scalar_one()

    # Get comments with user info
    stmt = (
        select(CheckInComment)
        .where(CheckInComment.check_in_id == check_in_id)
        .options(selectinload(CheckInComment.user))
        .order_by(CheckInComment.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    comments_result = await db.execute(stmt)
    comments = comments_result.scalars().all()

    # Convert to response format
    comment_responses = []
    for comment in comments:
        comment_responses.append(CheckInCommentResponse(
            id=comment.id,
            check_in_id=comment.check_in_id,
            user_id=comment.user_id,
            user_name=comment.user.name or comment.user.email,
            user_avatar_url=comment.user.avatar_url,
            content=comment.content,
            created_at=comment.created_at,
            updated_at=comment.updated_at
        ))

    return PaginatedCheckInComments(
        items=comment_responses,
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/{check_in_id}/comments", response_model=CheckInCommentResponse)
async def add_check_in_comment(
    check_in_id: int,
    comment_data: CheckInCommentCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to a check-in"""

    # Verify check-in exists and user can view it
    check_in_result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = check_in_result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    if not await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility):
        raise HTTPException(
            status_code=403, detail="Not authorized to comment on this check-in")

    # Create comment
    comment = CheckInComment(
        check_in_id=check_in_id,
        user_id=current_user.id,
        content=comment_data.content
    )

    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # Load user info for response
    await db.refresh(comment, ['user'])

    # Create activity for the comment
    try:
        await create_comment_activity(
            db=db,
            user_id=current_user.id,
            comment_id=comment.id,
            checkin_id=check_in_id,
            checkin_user_id=check_in.user_id,
            comment_content=comment_data.content
        )
    except Exception as e:
        # Log error but don't fail the comment creation
        print(
            f"Failed to create activity for comment on check-in {check_in_id}: {e}")

    return CheckInCommentResponse(
        id=comment.id,
        check_in_id=comment.check_in_id,
        user_id=comment.user_id,
        user_name=comment.user.name or comment.user.email,
        user_avatar_url=comment.user.avatar_url,
        content=comment.content,
        created_at=comment.created_at,
        updated_at=comment.updated_at
    )


@router.delete("/{check_in_id}/comments/{comment_id}")
async def delete_check_in_comment(
    check_in_id: int,
    comment_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a comment from a check-in (only comment author or check-in author can delete)"""

    # Get comment
    comment_result = await db.execute(
        select(CheckInComment).where(
            CheckInComment.id == comment_id,
            CheckInComment.check_in_id == check_in_id
        )
    )
    comment = comment_result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Check permissions (comment author or check-in author can delete)
    check_in_result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = check_in_result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    if comment.user_id != current_user.id and check_in.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this comment")

    await db.delete(comment)
    await db.commit()

    return {"message": "Comment deleted successfully"}


@router.get("/{check_in_id}/likes", response_model=PaginatedCheckInLikes)
async def get_check_in_likes(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get likes for a check-in"""

    # Verify check-in exists and user can view it
    check_in_result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = check_in_result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    if not await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility):
        raise HTTPException(
            status_code=403, detail="Not authorized to view this check-in")

    # Get total count
    total_result = await db.execute(
        select(func.count(CheckInLike.id)).where(
            CheckInLike.check_in_id == check_in_id)
    )
    total = total_result.scalar_one()

    # Get likes with user info
    stmt = (
        select(CheckInLike)
        .where(CheckInLike.check_in_id == check_in_id)
        .options(selectinload(CheckInLike.user))
        .order_by(CheckInLike.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    likes_result = await db.execute(stmt)
    likes = likes_result.scalars().all()

    # Convert to response format
    like_responses = []
    for like in likes:
        like_responses.append(CheckInLikeResponse(
            id=like.id,
            check_in_id=like.check_in_id,
            user_id=like.user_id,
            user_name=like.user.name or like.user.email,
            user_avatar_url=like.user.avatar_url,
            created_at=like.created_at
        ))

    return PaginatedCheckInLikes(
        items=like_responses,
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/{check_in_id}/like")
async def like_check_in(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Like a check-in"""

    # Verify check-in exists and user can view it
    check_in_result = await db.execute(select(CheckIn).where(CheckIn.id == check_in_id))
    check_in = check_in_result.scalar_one_or_none()

    if not check_in:
        raise HTTPException(status_code=404, detail="Check-in not found")

    if not await can_view_checkin(db, check_in.user_id, current_user.id, check_in.visibility):
        raise HTTPException(
            status_code=403, detail="Not authorized to like this check-in")

    # Check if already liked
    existing_like_result = await db.execute(
        select(CheckInLike).where(
            CheckInLike.check_in_id == check_in_id,
            CheckInLike.user_id == current_user.id
        )
    )
    existing_like = existing_like_result.scalar_one_or_none()

    if existing_like:
        raise HTTPException(
            status_code=400, detail="Already liked this check-in")

    # Create like
    like = CheckInLike(
        check_in_id=check_in_id,
        user_id=current_user.id
    )

    db.add(like)
    await db.commit()

    # Create activity for the like
    try:
        await create_like_activity(
            db=db,
            user_id=current_user.id,
            checkin_id=check_in_id,
            checkin_user_id=check_in.user_id,
            checkin_note=check_in.note
        )
    except Exception as e:
        # Log error but don't fail the like creation
        print(
            f"Failed to create activity for like on check-in {check_in_id}: {e}")

    return {"message": "Check-in liked successfully"}


@router.delete("/{check_in_id}/like")
async def unlike_check_in(
    check_in_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlike a check-in"""

    # Get existing like
    like_result = await db.execute(
        select(CheckInLike).where(
            CheckInLike.check_in_id == check_in_id,
            CheckInLike.user_id == current_user.id
        )
    )
    like = like_result.scalar_one_or_none()

    if not like:
        raise HTTPException(status_code=404, detail="Like not found")

    await db.delete(like)
    await db.commit()

    return {"message": "Check-in unliked successfully"}
