from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DMParticipantState, DMThread


async def has_block_between(db: AsyncSession, user_a_id: int, user_b_id: int) -> bool:
    """Return True if either user has blocked the other in any DM thread."""
    if user_a_id == user_b_id:
        return False

    pair_condition = or_(
        and_(DMThread.user_a_id == user_a_id, DMThread.user_b_id == user_b_id),
        and_(DMThread.user_a_id == user_b_id, DMThread.user_b_id == user_a_id),
    )

    stmt = (
        select(DMParticipantState.id)
        .join(DMThread, DMThread.id == DMParticipantState.thread_id)
        .where(pair_condition, DMParticipantState.blocked.is_(True))
        .limit(1)
    )

    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def has_user_blocked(
    db: AsyncSession,
    blocker_id: int,
    target_id: int,
) -> bool:
    """Return True if `blocker_id` has blocked `target_id`."""
    if blocker_id == target_id:
        return False

    pair_condition = or_(
        and_(DMThread.user_a_id == blocker_id, DMThread.user_b_id == target_id),
        and_(DMThread.user_a_id == target_id, DMThread.user_b_id == blocker_id),
    )

    stmt = (
        select(DMParticipantState.id)
        .join(DMThread, DMThread.id == DMParticipantState.thread_id)
        .where(
            pair_condition,
            DMParticipantState.user_id == blocker_id,
            DMParticipantState.blocked.is_(True),
        )
        .limit(1)
    )

    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None
