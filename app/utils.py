from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, select
from app.models import User, Friendship, Follow


async def are_friends(db: AsyncSession, user1_id: int, user2_id: int) -> bool:
    """
    Check if two users are friends (have an accepted friendship).

    Args:
        db: Database session
        user1_id: ID of the first user
        user2_id: ID of the second user

    Returns:
        True if users are friends, False otherwise
    """
    if user1_id == user2_id:
        return True  # Users are always "friends" with themselves

    result = await db.execute(
        select(Friendship).where(
            Friendship.status == "accepted",
            or_(
                and_(Friendship.requester_id == user1_id,
                     Friendship.addressee_id == user2_id),
                and_(Friendship.requester_id == user2_id,
                     Friendship.addressee_id == user1_id)
            )
        )
    )
    friendship = result.scalar_one_or_none()

    return friendship is not None


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
