from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta
import json

from ..database import get_db
from ..models import Activity, User, Follow, CheckIn, CheckInLike, CheckInComment, Review
from ..utils import can_view_checkin
from ..schemas import (
    ActivityItem,
    PaginatedActivityFeed,
    ActivityFeedFilters,
)
from ..services.jwt_service import JWTService
from ..services.storage import StorageService


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


router = APIRouter(
    prefix="/activity",
    tags=["activity feed"],
    responses={
        400: {"description": "Invalid filter parameters"},
        500: {"description": "Internal server error"}
    }
)


async def _create_activity(
    db: AsyncSession,
    user_id: int,
    activity_type: str,
    activity_data: dict
) -> Activity:
    """Helper function to create an activity record"""
    activity = Activity(
        user_id=user_id,
        activity_type=activity_type,
        activity_data=json.dumps(activity_data)
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return activity


async def _filter_activity_by_privacy(
    db: AsyncSession,
    activity: Activity,
    current_user_id: int
) -> bool:
    """Filter activity based on privacy settings"""
    try:
        activity_data = json.loads(activity.activity_data)
    except json.JSONDecodeError:
        return True  # If we can't parse, allow it

    # Filter check-in activities based on visibility
    if activity.activity_type == "checkin":
        checkin_id = activity_data.get("checkin_id")
        if checkin_id:
            # Get check-in visibility
            checkin_query = select(CheckIn).where(CheckIn.id == checkin_id)
            checkin_result = await db.execute(checkin_query)
            checkin = checkin_result.scalar_one_or_none()

            if checkin:
                # Check if current user can view this check-in
                can_view = await can_view_checkin(
                    db,
                    checkin.user_id,
                    current_user_id,
                    checkin.visibility
                )
                return can_view

    return True  # Allow all other activity types


@router.get("/feed", response_model=PaginatedActivityFeed)
async def get_activity_feed(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    activity_types: Optional[str] = Query(
        None, description="Comma-separated list of activity types to filter by"),
    since: Optional[datetime] = Query(
        None, description="Filter activities created after this timestamp"),
    until: Optional[datetime] = Query(
        None, description="Filter activities created before this timestamp"),
):
    """
    Get activity feed from followed users.

    **Authentication Required:** Yes

    **Features:**
    - Shows activities from users you follow
    - Real-time social timeline
    - Privacy-respecting content
    - Rich activity data

    **Activity Types:**
    - Check-ins with photos and notes
    - Reviews and ratings
    - Follow relationships
    - Collection creations
    - Likes and comments

    **Privacy Enforcement:**
    - Only shows content user has permission to see
    - Respects visibility settings (public, followers, private)
    - Followers can see followers-only content

    **Response Format:**
    - Activity type and timestamp
    - User information (name, avatar)
    - Activity-specific data (place, photos, etc.)
    - Pagination information

    **Use Cases:**
    - Social timeline
    - Friend activity monitoring
    - Content discovery
    - Social networking features
    """

    # Get list of users the current user follows
    following_query = select(Follow.followee_id).where(
        Follow.follower_id == current_user.id)
    following_result = await db.execute(following_query)
    following_ids = [row[0] for row in following_result.fetchall()]

    if not following_ids:
        # If user doesn't follow anyone, return empty feed
        return PaginatedActivityFeed(items=[], total=0, limit=limit, offset=offset)

    # Build base query for activities from followed users
    base_query = select(Activity).where(Activity.user_id.in_(following_ids))

    # Apply filters
    if activity_types:
        types_list = [t.strip() for t in activity_types.split(",")]
        base_query = base_query.where(Activity.activity_type.in_(types_list))

    if since:
        base_query = base_query.where(Activity.created_at >= since)

    if until:
        base_query = base_query.where(Activity.created_at <= until)

    # Get total count
    count_query = select(func.count(Activity.id)).select_from(
        base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get activities with user info
    activities_query = (
        base_query
        .options(selectinload(Activity.user))
        .order_by(desc(Activity.created_at))
        .offset(offset)
        .limit(limit)
    )

    activities_result = await db.execute(activities_query)
    activities = activities_result.scalars().all()

    # Convert to response format with privacy filtering
    activity_items = []
    for activity in activities:
        # Filter by privacy settings
        if not await _filter_activity_by_privacy(db, activity, current_user.id):
            continue

        try:
            activity_data = json.loads(activity.activity_data)
        except json.JSONDecodeError:
            activity_data = {}

        activity_items.append(ActivityItem(
            id=activity.id,
            user_id=activity.user_id,
            user_name=activity.user.name or f"User {activity.user.id}",
            user_avatar_url=_convert_single_to_signed_url(
                activity.user.avatar_url),
            activity_type=activity.activity_type,
            activity_data=activity_data,
            created_at=activity.created_at
        ))

    return PaginatedActivityFeed(
        items=activity_items,
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/feed/filtered", response_model=PaginatedActivityFeed)
async def get_filtered_activity_feed(
    filters: ActivityFeedFilters,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get filtered activity feed with advanced filtering options"""

    # Get list of users the current user follows
    following_query = select(Follow.followee_id).where(
        Follow.follower_id == current_user.id)
    following_result = await db.execute(following_query)
    following_ids = [row[0] for row in following_result.fetchall()]

    if not following_ids:
        return PaginatedActivityFeed(items=[], total=0, limit=filters.limit, offset=filters.offset)

    # Build base query
    base_query = select(Activity).where(Activity.user_id.in_(following_ids))

    # Apply filters
    if filters.activity_types:
        base_query = base_query.where(
            Activity.activity_type.in_(filters.activity_types))

    if filters.user_ids:
        # Intersect with followed users
        valid_user_ids = list(set(following_ids) & set(filters.user_ids))
        if not valid_user_ids:
            return PaginatedActivityFeed(items=[], total=0, limit=filters.limit, offset=filters.offset)
        base_query = base_query.where(Activity.user_id.in_(valid_user_ids))

    if filters.since:
        base_query = base_query.where(Activity.created_at >= filters.since)

    if filters.until:
        base_query = base_query.where(Activity.created_at <= filters.until)

    # Get total count
    count_query = select(func.count(Activity.id)).select_from(
        base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get activities
    activities_query = (
        base_query
        .options(selectinload(Activity.user))
        .order_by(desc(Activity.created_at))
        .offset(filters.offset)
        .limit(filters.limit)
    )

    activities_result = await db.execute(activities_query)
    activities = activities_result.scalars().all()

    # Convert to response format with privacy filtering
    activity_items = []
    for activity in activities:
        # Filter by privacy settings
        if not await _filter_activity_by_privacy(db, activity, current_user.id):
            continue

        try:
            activity_data = json.loads(activity.activity_data)
        except json.JSONDecodeError:
            activity_data = {}

        activity_items.append(ActivityItem(
            id=activity.id,
            user_id=activity.user_id,
            user_name=activity.user.name or f"User {activity.user.id}",
            user_avatar_url=_convert_single_to_signed_url(
                activity.user.avatar_url),
            activity_type=activity.activity_type,
            activity_data=activity_data,
            created_at=activity.created_at
        ))

    return PaginatedActivityFeed(
        items=activity_items,
        total=total,
        limit=filters.limit,
        offset=filters.offset
    )


# Activity creation endpoints (called by other routers)

async def create_checkin_activity(
    db: AsyncSession,
    user_id: int,
    checkin_id: int,
    place_name: str,
    note: str = None
) -> Activity:
    """Create activity for a new check-in"""
    activity_data = {
        "checkin_id": checkin_id,
        "place_name": place_name,
        "note": note
    }
    return await _create_activity(db, user_id, "checkin", activity_data)


async def create_like_activity(
    db: AsyncSession,
    user_id: int,
    checkin_id: int,
    checkin_user_id: int,
    checkin_note: str = None
) -> Activity:
    """Create activity for liking a check-in"""
    activity_data = {
        "checkin_id": checkin_id,
        "checkin_user_id": checkin_user_id,
        "checkin_note": checkin_note
    }
    return await _create_activity(db, user_id, "like", activity_data)


async def create_comment_activity(
    db: AsyncSession,
    user_id: int,
    comment_id: int,
    checkin_id: int,
    checkin_user_id: int,
    comment_content: str
) -> Activity:
    """Create activity for commenting on a check-in"""
    activity_data = {
        "comment_id": comment_id,
        "checkin_id": checkin_id,
        "checkin_user_id": checkin_user_id,
        "comment_content": comment_content
    }
    return await _create_activity(db, user_id, "comment", activity_data)


async def create_follow_activity(
    db: AsyncSession,
    follower_id: int,
    followee_id: int,
    followee_name: str
) -> Activity:
    """Create activity for following a user"""
    activity_data = {
        "followee_id": followee_id,
        "followee_name": followee_name
    }
    return await _create_activity(db, follower_id, "follow", activity_data)


async def create_review_activity(
    db: AsyncSession,
    user_id: int,
    review_id: int,
    place_name: str,
    rating: float,
    review_text: str = None
) -> Activity:
    """Create activity for posting a review"""
    activity_data = {
        "review_id": review_id,
        "place_name": place_name,
        "rating": rating,
        "review_text": review_text
    }
    return await _create_activity(db, user_id, "review", activity_data)


async def create_collection_activity(
    db: AsyncSession,
    user_id: int,
    collection_id: int,
    collection_name: str
) -> Activity:
    """Create activity for creating a collection"""
    activity_data = {
        "collection_id": collection_id,
        "collection_name": collection_name
    }
    return await _create_activity(db, user_id, "collection", activity_data)
