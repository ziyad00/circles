from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User, UserBlock
from ..schemas import (
    GlobalBlockCreate,
    GlobalBlockResponse,
    PaginatedBlocks,
    BlockStatusResponse,
)
from ..services.jwt_service import JWTService
from ..services.block_service import (
    create_global_block,
    remove_global_block,
    get_user_blocks,
    get_blocked_by_users,
    has_user_blocked,
)

router = APIRouter(prefix="/blocks", tags=["blocking"])


@router.post("/", response_model=GlobalBlockResponse, status_code=201)
async def create_block(
    payload: GlobalBlockCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Block a user globally across all features.

    **Authentication Required:** Yes

    **Features:**
    - Block users permanently or temporarily
    - Add optional reason for blocking
    - Automatically removes follow relationships
    - Prevents all interactions with blocked user

    **Use Cases:**
    - Block harassing users
    - Temporary blocks for cooling off
    - Privacy protection
    """
    # Validate the user exists
    user_result = await db.execute(
        select(User).where(User.id == payload.blocked_user_id)
    )
    blocked_user = user_result.scalar_one_or_none()
    if not blocked_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Cannot block yourself
    if payload.blocked_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot block yourself")

    try:
        # Create the global block
        block = await create_global_block(
            db=db,
            blocker_id=current_user.id,
            blocked_id=payload.blocked_user_id,
            reason=payload.reason,
            block_type=payload.block_type,
            expires_at=payload.expires_at
        )

        # Remove follow relationships if blocking
        from ..models import Follow
        # Remove follow relationship if current user follows the blocked user
        follow_res = await db.execute(
            select(Follow).where(
                Follow.follower_id == current_user.id,
                Follow.followee_id == payload.blocked_user_id
            )
        )
        if follow_res.scalar_one_or_none():
            await db.execute(
                select(Follow).where(
                    Follow.follower_id == current_user.id,
                    Follow.followee_id == payload.blocked_user_id
                ).delete()
            )

        # Remove follow relationship if blocked user follows current user
        follow_res = await db.execute(
            select(Follow).where(
                Follow.follower_id == payload.blocked_user_id,
                Follow.followee_id == current_user.id
            )
        )
        if follow_res.scalar_one_or_none():
            await db.execute(
                select(Follow).where(
                    Follow.follower_id == payload.blocked_user_id,
                    Follow.followee_id == current_user.id
                ).delete()
            )

        await db.commit()

        # Prepare response with user info
        response_data = GlobalBlockResponse.model_validate(block)
        response_data.blocked_user = {
            "id": blocked_user.id,
            "username": blocked_user.username,
            "name": blocked_user.name,
            "avatar_url": blocked_user.avatar_url
        }

        return response_data

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{blocked_user_id}", status_code=204)
async def unblock_user(
    blocked_user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Unblock a user.

    **Authentication Required:** Yes

    **Features:**
    - Remove global block
    - Restore ability to interact with user
    - Does not restore follow relationships

    **Use Cases:**
    - Change of mind about blocking
    - Resolving conflicts
    - Temporary unblocking
    """
    success = await remove_global_block(
        db=db,
        blocker_id=current_user.id,
        blocked_id=blocked_user_id
    )

    if not success:
        raise HTTPException(status_code=404, detail="Block not found")


@router.get("/", response_model=PaginatedBlocks)
async def list_blocked_users(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List all users blocked by the current user.

    **Authentication Required:** Yes

    **Features:**
    - Paginated list of blocked users
    - Includes block details (reason, type, expiration)
    - Shows blocked user information

    **Use Cases:**
    - Review blocked users
    - Manage blocking settings
    - Check block status
    """
    blocks = await get_user_blocks(
        db=db,
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )

    # Get total count
    total_result = await db.execute(
        select(func.count(UserBlock.id)).where(
            UserBlock.blocker_id == current_user.id)
    )
    total = total_result.scalar_one()

    # Get user info for each block
    blocked_user_ids = [block.blocked_id for block in blocks]
    users_result = await db.execute(
        select(User).where(User.id.in_(blocked_user_ids))
    )
    users = {user.id: user for user in users_result.scalars().all()}

    # Prepare response
    items = []
    for block in blocks:
        response_data = GlobalBlockResponse.model_validate(block)
        if block.blocked_id in users:
            user = users[block.blocked_id]
            response_data.blocked_user = {
                "id": user.id,
                "username": user.username,
                "name": user.name,
                "avatar_url": user.avatar_url
            }
        items.append(response_data)

    return PaginatedBlocks(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/blocked-by", response_model=PaginatedBlocks)
async def list_users_who_blocked_me(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List all users who have blocked the current user.

    **Authentication Required:** Yes

    **Features:**
    - Paginated list of users who blocked current user
    - Shows block details (reason, type, expiration)
    - Limited user information for privacy

    **Use Cases:**
    - Understand why interactions failed
    - Review blocking history
    - Privacy awareness
    """
    blocks = await get_blocked_by_users(
        db=db,
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )

    # Get total count
    total_result = await db.execute(
        select(func.count(UserBlock.id)).where(
            UserBlock.blocked_id == current_user.id)
    )
    total = total_result.scalar_one()

    # Get user info for each block (limited info for privacy)
    blocker_user_ids = [block.blocker_id for block in blocks]
    users_result = await db.execute(
        select(User).where(User.id.in_(blocker_user_ids))
    )
    users = {user.id: user for user in users_result.scalars().all()}

    # Prepare response
    items = []
    for block in blocks:
        response_data = GlobalBlockResponse.model_validate(block)
        if block.blocker_id in users:
            user = users[block.blocker_id]
            # Limited info for privacy
            response_data.blocked_user = {
                "id": user.id,
                "username": user.username,
                # Don't include name, avatar for privacy
            }
        items.append(response_data)

    return PaginatedBlocks(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/status/{user_id}", response_model=BlockStatusResponse)
async def get_block_status(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if a user is blocked by the current user.

    **Authentication Required:** Yes

    **Features:**
    - Check block status between users
    - Get block details if blocked
    - Privacy-aware response

    **Use Cases:**
    - Check before attempting interaction
    - UI state management
    - Block status verification
    """
    # Check if current user has blocked the target user
    is_blocked = await has_user_blocked(
        db=db,
        blocker_id=current_user.id,
        target_id=user_id
    )

    if not is_blocked:
        return BlockStatusResponse(is_blocked=False)

    # Get block details
    block_result = await db.execute(
        select(UserBlock).where(
            UserBlock.blocker_id == current_user.id,
            UserBlock.blocked_id == user_id
        )
    )
    block = block_result.scalar_one_or_none()

    if block:
        return BlockStatusResponse(
            is_blocked=True,
            block_type=block.block_type,
            expires_at=block.expires_at,
            reason=block.reason,
            created_at=block.created_at
        )

    return BlockStatusResponse(is_blocked=True)


@router.get("/count")
async def get_block_counts(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get blocking statistics for the current user.

    **Authentication Required:** Yes

    **Features:**
    - Count of users blocked by current user
    - Count of users who blocked current user
    - Quick statistics for UI

    **Use Cases:**
    - Dashboard statistics
    - Block management overview
    - Privacy metrics
    """
    # Count users blocked by current user
    blocked_count_result = await db.execute(
        select(func.count(UserBlock.id)).where(
            UserBlock.blocker_id == current_user.id)
    )
    blocked_count = blocked_count_result.scalar_one()

    # Count users who blocked current user
    blocked_by_count_result = await db.execute(
        select(func.count(UserBlock.id)).where(
            UserBlock.blocked_id == current_user.id)
    )
    blocked_by_count = blocked_by_count_result.scalar_one()

    return {
        "users_blocked": blocked_count,
        "blocked_by_users": blocked_by_count,
        "total_blocks": blocked_count + blocked_by_count
    }
