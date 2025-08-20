from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta
import json

from ..database import get_db
from ..models import Activity, User, Follow, CheckIn, CheckInLike, CheckInComment, Review, CheckInCollection
from ..schemas import (
    ActivityItem,
    PaginatedActivityFeed,
    ActivityFeedFilters,
)
from ..services.jwt_service import JWTService
from ..utils import can_view_checkin

router = APIRouter(prefix="/activity", tags=["activity"])


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


@router.get("/feed", response_model=PaginatedActivityFeed)
async def get_activity_feed(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    activity_types: str = Query(
        None, description="Comma-separated activity types to filter"),
    since: datetime = Query(
        None, description="Show activities since this time"),
    until: datetime = Query(
        None, description="Show activities until this time"),
):
    """Get activity feed for the current user (activities from followed users)"""

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

    # Convert to response format
    activity_items = []
    for activity in activities:
        try:
            activity_data = json.loads(activity.activity_data)
        except json.JSONDecodeError:
            activity_data = {}

        activity_items.append(ActivityItem(
            id=activity.id,
            user_id=activity.user_id,
            user_name=activity.user.name or activity.user.email,
            user_avatar_url=activity.user.avatar_url,
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

    # Convert to response format
    activity_items = []
    for activity in activities:
        try:
            activity_data = json.loads(activity.activity_data)
        except json.JSONDecodeError:
            activity_data = {}

        activity_items.append(ActivityItem(
            id=activity.id,
            user_id=activity.user_id,
            user_name=activity.user.name or activity.user.email,
            user_avatar_url=activity.user.avatar_url,
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


@router.get("/my-activities", response_model=PaginatedActivityFeed)
async def get_my_activities(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get current user's own activities"""

    # Get total count
    count_query = select(func.count(Activity.id)).where(
        Activity.user_id == current_user.id)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get activities
    activities_query = (
        select(Activity)
        .where(Activity.user_id == current_user.id)
        .options(selectinload(Activity.user))
        .order_by(desc(Activity.created_at))
        .offset(offset)
        .limit(limit)
    )

    activities_result = await db.execute(activities_query)
    activities = activities_result.scalars().all()

    # Convert to response format
    activity_items = []
    for activity in activities:
        try:
            activity_data = json.loads(activity.activity_data)
        except json.JSONDecodeError:
            activity_data = {}

        activity_items.append(ActivityItem(
            id=activity.id,
            user_id=activity.user_id,
            user_name=activity.user.name or activity.user.email,
            user_avatar_url=activity.user.avatar_url,
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


@router.get("/user/{user_id}/activities", response_model=PaginatedActivityFeed)
async def get_user_activities(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get activities for a specific user (if current user follows them or they're public)"""

    # Check if current user follows the target user
    follow_query = select(Follow).where(
        Follow.follower_id == current_user.id,
        Follow.followee_id == user_id
    )
    follow_result = await db.execute(follow_query)
    is_following = follow_result.scalar_one_or_none() is not None

    if not is_following and user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to view this user's activities")

    # Get total count
    count_query = select(func.count(Activity.id)).where(
        Activity.user_id == user_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get activities
    activities_query = (
        select(Activity)
        .where(Activity.user_id == user_id)
        .options(selectinload(Activity.user))
        .order_by(desc(Activity.created_at))
        .offset(offset)
        .limit(limit)
    )

    activities_result = await db.execute(activities_query)
    activities = activities_result.scalars().all()

    # Convert to response format
    activity_items = []
    for activity in activities:
        try:
            activity_data = json.loads(activity.activity_data)
        except json.JSONDecodeError:
            activity_data = {}

        activity_items.append(ActivityItem(
            id=activity.id,
            user_id=activity.user_id,
            user_name=activity.user.name or activity.user.email,
            user_avatar_url=activity.user.avatar_url,
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
