from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DMParticipantState, DMThread, UserBlock


async def has_block_between(db: AsyncSession, user_a_id: int, user_b_id: int) -> bool:
    """Return True if either user has blocked the other globally or in any DM thread."""
    if user_a_id == user_b_id:
        return False

    # Check global blocking first
    global_block_stmt = (
        select(UserBlock.id)
        .where(
            or_(
                and_(UserBlock.blocker_id == user_a_id,
                     UserBlock.blocked_id == user_b_id),
                and_(UserBlock.blocker_id == user_b_id,
                     UserBlock.blocked_id == user_a_id),
            ),
            or_(
                UserBlock.block_type == "permanent",
                and_(
                    UserBlock.block_type == "temporary",
                    UserBlock.expires_at > datetime.now(timezone.utc)
                )
            )
        )
        .limit(1)
    )

    result = await db.execute(global_block_stmt)
    if result.scalar_one_or_none() is not None:
        return True

    # Check DM-specific blocking
    pair_condition = or_(
        and_(DMThread.user_a_id == user_a_id, DMThread.user_b_id == user_b_id),
        and_(DMThread.user_a_id == user_b_id, DMThread.user_b_id == user_a_id),
    )

    dm_block_stmt = (
        select(DMParticipantState.id)
        .join(DMThread, DMThread.id == DMParticipantState.thread_id)
        .where(pair_condition, DMParticipantState.blocked.is_(True))
        .limit(1)
    )

    result = await db.execute(dm_block_stmt)
    return result.scalar_one_or_none() is not None


async def has_user_blocked(
    db: AsyncSession,
    blocker_id: int,
    target_id: int,
) -> bool:
    """Return True if `blocker_id` has blocked `target_id` globally or in DMs."""
    if blocker_id == target_id:
        return False

    # Check global blocking first
    global_block_stmt = (
        select(UserBlock.id)
        .where(
            UserBlock.blocker_id == blocker_id,
            UserBlock.blocked_id == target_id,
            or_(
                UserBlock.block_type == "permanent",
                and_(
                    UserBlock.block_type == "temporary",
                    UserBlock.expires_at > datetime.now(timezone.utc)
                )
            )
        )
        .limit(1)
    )

    result = await db.execute(global_block_stmt)
    if result.scalar_one_or_none() is not None:
        return True

    # Check DM-specific blocking
    pair_condition = or_(
        and_(DMThread.user_a_id == blocker_id,
             DMThread.user_b_id == target_id),
        and_(DMThread.user_a_id == target_id,
             DMThread.user_b_id == blocker_id),
    )

    dm_block_stmt = (
        select(DMParticipantState.id)
        .join(DMThread, DMThread.id == DMParticipantState.thread_id)
        .where(
            pair_condition,
            DMParticipantState.user_id == blocker_id,
            DMParticipantState.blocked.is_(True),
        )
        .limit(1)
    )

    result = await db.execute(dm_block_stmt)
    return result.scalar_one_or_none() is not None


async def create_global_block(
    db: AsyncSession,
    blocker_id: int,
    blocked_id: int,
    reason: str = None,
    block_type: str = "permanent",
    expires_at: datetime = None
) -> UserBlock:
    """Create a global block between users."""
    if blocker_id == blocked_id:
        raise ValueError("Cannot block yourself")

    # Check if block already exists
    existing_block = await db.execute(
        select(UserBlock).where(
            UserBlock.blocker_id == blocker_id,
            UserBlock.blocked_id == blocked_id
        )
    )
    if existing_block.scalar_one_or_none():
        raise ValueError("User is already blocked")

    block = UserBlock(
        blocker_id=blocker_id,
        blocked_id=blocked_id,
        reason=reason,
        block_type=block_type,
        expires_at=expires_at
    )
    db.add(block)
    await db.commit()
    await db.refresh(block)
    return block


async def remove_global_block(
    db: AsyncSession,
    blocker_id: int,
    blocked_id: int
) -> bool:
    """Remove a global block between users."""
    result = await db.execute(
        select(UserBlock).where(
            UserBlock.blocker_id == blocker_id,
            UserBlock.blocked_id == blocked_id
        )
    )
    block = result.scalar_one_or_none()
    if block:
        await db.delete(block)
        await db.commit()
        return True
    return False


async def get_user_blocks(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
    offset: int = 0
) -> list[UserBlock]:
    """Get all users blocked by the given user."""
    result = await db.execute(
        select(UserBlock)
        .where(UserBlock.blocker_id == user_id)
        .order_by(UserBlock.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def get_blocked_by_users(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
    offset: int = 0
) -> list[UserBlock]:
    """Get all users who have blocked the given user."""
    result = await db.execute(
        select(UserBlock)
        .where(UserBlock.blocked_id == user_id)
        .order_by(UserBlock.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
