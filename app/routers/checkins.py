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
from ..services.storage import StorageService


def _organize_comments_threaded(comments: list[CheckInCommentResponse]) -> list[CheckInCommentResponse]:
    """Organize flat comment list into threaded structure"""
    # Create a map for quick lookup
    comment_map = {comment.id: comment for comment in comments}

    # Separate top-level comments and replies
    top_level = []

    for comment in comments:
        if comment.reply_to_id is None:
            # This is a top-level comment
            top_level.append(comment)
        else:
            # This is a reply, add it to parent's replies list
            parent = comment_map.get(comment.reply_to_id)
            if parent:
                parent.replies.append(comment)

    # Sort replies by creation time
    for comment in top_level:
        comment.replies.sort(key=lambda x: x.created_at)

    return top_level


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
        user_avatar_url=_convert_single_to_signed_url(
            check_in.user.avatar_url),
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
    threaded: bool = Query(False, description="Return comments in threaded format"),
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

    # Get comments with user info and reply relationships
    stmt = (
        select(CheckInComment)
        .options(selectinload(CheckInComment.user))
        .options(selectinload(CheckInComment.reply_to).selectinload(CheckInComment.user))
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

    # Convert comments to response objects
    comment_responses = [
        CheckInCommentResponse(
            id=comment.id,
            check_in_id=comment.check_in_id,
            user_id=comment.user_id,
            user_name=comment.user.name or f"User {comment.user.id}",
            user_avatar_url=_convert_single_to_signed_url(
                comment.user.avatar_url),
            content=comment.content,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            reply_to_id=comment.reply_to_id,
            reply_to_text=comment.reply_to_text,
            reply_to_user_name=comment.reply_to.user.name if comment.reply_to else None,
            replies=[],
        )
        for comment in comments
    ]

    # If threaded view is requested, organize into threads
    if threaded:
        items = _organize_comments_threaded(comment_responses)
    else:
        items = comment_responses

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

    # Validate reply_to_id if provided
    reply_to_text = None
    if comment_data.reply_to_id:
        reply_comment_result = await db.execute(
            select(CheckInComment)
            .options(selectinload(CheckInComment.user))
            .where(
                CheckInComment.id == comment_data.reply_to_id,
                CheckInComment.check_in_id == check_in_id
            )
        )
        reply_comment = reply_comment_result.scalar_one_or_none()
        if not reply_comment:
            raise HTTPException(
                status_code=404,
                detail="Reply target comment not found or doesn't belong to this check-in"
            )
        # Store quoted text for reply context
        reply_to_text = reply_comment.content[:200] + ("..." if len(reply_comment.content) > 200 else "")

    # Create comment
    comment = CheckInComment(
        check_in_id=check_in_id,
        user_id=current_user.id,
        content=comment_data.content,
        reply_to_id=comment_data.reply_to_id,
        reply_to_text=reply_to_text,
    )

    db.add(comment)
    await db.commit()
    await db.refresh(comment, ['user', 'reply_to'])

    # Get reply_to_user_name if this is a reply
    reply_to_user_name = None
    if comment.reply_to:
        await db.refresh(comment.reply_to, ['user'])
        reply_to_user_name = comment.reply_to.user.name or f"User {comment.reply_to.user.id}"

    return CheckInCommentResponse(
        id=comment.id,
        check_in_id=comment.check_in_id,
        user_id=comment.user_id,
        user_name=comment.user.name or f"User {comment.user.id}",
        user_avatar_url=_convert_single_to_signed_url(comment.user.avatar_url),
        content=comment.content,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        reply_to_id=comment.reply_to_id,
        reply_to_text=comment.reply_to_text,
        reply_to_user_name=reply_to_user_name,
        replies=[],
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
            user_avatar_url=_convert_single_to_signed_url(
                like.user.avatar_url),
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
