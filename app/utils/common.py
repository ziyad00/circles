from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, select
from math import radians, cos, sin, asin, sqrt
from app.models import User, Follow


"""Friends helpers removed; using follows instead."""


async def can_view_checkin(db: AsyncSession, checkin_user_id: int, viewer_user_id: int, visibility: str) -> bool:
    """
    Check if a user can view a check-in based on its visibility setting.

    Args:
        db: Database session
        checkin_user_id: ID of the user who created the check-in
        viewer_user_id: ID of the user trying to view the check-in
        visibility: Visibility level of the check-in ("public", "followers", "private")

    Returns:
        True if the viewer can see the check-in, False otherwise
    """
    return await _check_visibility_access(db, checkin_user_id, viewer_user_id, visibility)


async def _check_visibility_access(db: AsyncSession, owner_user_id: int, viewer_user_id: int, visibility: str) -> bool:
    """
    Core privacy check function used across all privacy-controlled content.

    Args:
        db: Database session
        owner_user_id: ID of the user who owns the content
        viewer_user_id: ID of the user trying to view the content
        visibility: Visibility level ("public", "followers", "private")

    Returns:
        True if the viewer can see the content, False otherwise
    """
    if visibility == "public":
        return True
    elif visibility == "private":
        return owner_user_id == viewer_user_id
    elif visibility == "followers":
        # viewer must follow owner
        if owner_user_id == viewer_user_id:
            return True
        result = await db.execute(
            select(Follow).where(Follow.follower_id == viewer_user_id,
                                 Follow.followee_id == owner_user_id)
        )
        return result.scalar_one_or_none() is not None
    else:
        return False  # Unknown visibility level


async def can_view_profile(db: AsyncSession, profile_user: User, viewer_user_id: int) -> bool:
    """
    Check if a user can view another user's profile.

    Args:
        db: Database session
        profile_user: User whose profile is being viewed
        viewer_user_id: ID of the user trying to view the profile

    Returns:
        True if the viewer can see the profile, False otherwise
    """
    profile_visibility = getattr(profile_user, 'profile_visibility', 'public')
    return await _check_visibility_access(db, profile_user.id, viewer_user_id, profile_visibility)


async def can_view_follower_list(db: AsyncSession, profile_user: User, viewer_user_id: int) -> bool:
    """
    Check if a user can view another user's follower list.
    """
    visibility = getattr(profile_user, 'follower_list_visibility', 'public')
    return await _check_visibility_access(db, profile_user.id, viewer_user_id, visibility)


async def can_view_following_list(db: AsyncSession, profile_user: User, viewer_user_id: int) -> bool:
    """
    Check if a user can view another user's following list.
    """
    visibility = getattr(profile_user, 'following_list_visibility', 'public')
    return await _check_visibility_access(db, profile_user.id, viewer_user_id, visibility)


async def can_view_stats(db: AsyncSession, profile_user: User, viewer_user_id: int) -> bool:
    """
    Check if a user can view another user's stats (follower count, etc.).
    """
    visibility = getattr(profile_user, 'stats_visibility', 'public')
    return await _check_visibility_access(db, profile_user.id, viewer_user_id, visibility)


async def can_view_collection(db: AsyncSession, collection_user_id: int, viewer_user_id: int, visibility: str) -> bool:
    """
    Check if a user can view a collection based on its visibility setting.
    """
    return await _check_visibility_access(db, collection_user_id, viewer_user_id, visibility)


async def should_appear_in_search(db: AsyncSession, profile_user: User, viewer_user_id: int) -> bool:
    """
    Check if a user should appear in search results for another user.
    """
    search_visibility = getattr(profile_user, 'search_visibility', 'public')
    return await _check_visibility_access(db, profile_user.id, viewer_user_id, search_visibility)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two points in kilometers using the Haversine formula."""
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    earth_radius_km = 6371.0
    return earth_radius_km * c
