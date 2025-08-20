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
        visibility: Visibility level of the check-in ("public", "friends", "private")

    Returns:
        True if the viewer can see the check-in, False otherwise
    """
    if visibility == "public":
        return True
    elif visibility == "private":
        return checkin_user_id == viewer_user_id
    elif visibility == "friends":
        # friends now maps to followers: viewer must follow owner
        if checkin_user_id == viewer_user_id:
            return True
        result = await db.execute(
            select(Follow).where(Follow.follower_id == viewer_user_id,
                                 Follow.followee_id == checkin_user_id)
        )
        return result.scalar_one_or_none() is not None
    else:
        return False  # Unknown visibility level


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two points in kilometers using the Haversine formula."""
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    earth_radius_km = 6371.0
    return earth_radius_km * c
