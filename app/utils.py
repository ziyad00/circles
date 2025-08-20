from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, select
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
