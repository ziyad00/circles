from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, select, func
from typing import List
from datetime import datetime

from app.database import get_db
from app.models import User, Friendship
from app.schemas import (
    FriendRequestCreate, FriendRequestResponse, FriendRequestUpdate,
    FriendResponse, PaginatedFriends, PaginatedFriendRequests,
    FriendshipStatusEnum
)
from app.services.jwt_service import JWTService

router = APIRouter(prefix="/friends", tags=["friends"])


@router.post("/requests", response_model=FriendRequestResponse)
async def send_friend_request(
    request: FriendRequestCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a friend request to another user by email."""
    # Find the addressee by email
    result = await db.execute(select(User).where(User.email == request.addressee_email))
    addressee = result.scalar_one_or_none()
    if not addressee:
        raise HTTPException(status_code=404, detail="User not found")

    if addressee.id == current_user.id:
        raise HTTPException(
            status_code=400, detail="Cannot send friend request to yourself")

    # Check if friendship already exists
    result = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.requester_id == current_user.id,
                     Friendship.addressee_id == addressee.id),
                and_(Friendship.requester_id == addressee.id,
                     Friendship.addressee_id == current_user.id)
            )
        )
    )
    existing_friendship = result.scalar_one_or_none()

    if existing_friendship:
        if existing_friendship.status == "accepted":
            raise HTTPException(status_code=400, detail="Already friends")
        elif existing_friendship.status == "pending":
            if existing_friendship.requester_id == current_user.id:
                raise HTTPException(
                    status_code=400, detail="Friend request already sent")
            else:
                raise HTTPException(
                    status_code=400, detail="Friend request already received")
        elif existing_friendship.status == "rejected":
            # Allow resending after rejection
            existing_friendship.status = "pending"
            existing_friendship.requester_id = current_user.id
            existing_friendship.addressee_id = addressee.id
            await db.commit()
            await db.refresh(existing_friendship)
            return existing_friendship

    # Create new friendship
    friendship = Friendship(
        requester_id=current_user.id,
        addressee_id=addressee.id,
        status="pending"
    )
    db.add(friendship)
    await db.commit()
    await db.refresh(friendship)

    return friendship


@router.put("/requests/{request_id}", response_model=FriendRequestResponse)
async def respond_to_friend_request(
    request_id: int,
    response: FriendRequestUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Accept or reject a friend request."""
    result = await db.execute(
        select(Friendship).where(
            Friendship.id == request_id,
            Friendship.addressee_id == current_user.id,
            Friendship.status == "pending"
        )
    )
    friendship = result.scalar_one_or_none()

    if not friendship:
        raise HTTPException(status_code=404, detail="Friend request not found")

    friendship.status = response.status
    await db.commit()
    await db.refresh(friendship)

    return friendship


@router.get("/requests", response_model=PaginatedFriendRequests)
async def list_friend_requests(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """List pending friend requests received by the current user."""
    # Get total count
    count_result = await db.execute(
        select(func.count(Friendship.id)).where(
            Friendship.addressee_id == current_user.id,
            Friendship.status == "pending"
        )
    )
    total = count_result.scalar_one()

    # Get paginated requests
    result = await db.execute(
        select(Friendship).where(
            Friendship.addressee_id == current_user.id,
            Friendship.status == "pending"
        ).offset(offset).limit(limit)
    )
    requests = result.scalars().all()

    return PaginatedFriendRequests(
        items=requests,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("", response_model=PaginatedFriends)
async def list_friends(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """List all accepted friends of the current user."""
    # Get all accepted friendships where current user is either requester or addressee
    result = await db.execute(
        select(Friendship).where(
            Friendship.status == "accepted",
            or_(
                Friendship.requester_id == current_user.id,
                Friendship.addressee_id == current_user.id
            )
        ).offset(offset).limit(limit)
    )
    friendships = result.scalars().all()

    friends = []
    for friendship in friendships:
        # Determine which user is the friend (not the current user)
        friend_id = friendship.addressee_id if friendship.requester_id == current_user.id else friendship.requester_id
        friend_result = await db.execute(select(User).where(User.id == friend_id))
        friend = friend_result.scalar_one_or_none()

        if friend:
            friends.append(FriendResponse(
                id=friend.id,
                email=friend.email,
                is_verified=friend.is_verified,
                created_at=friend.created_at,
                friendship_id=friendship.id,
                friendship_created_at=friendship.created_at
            ))

    # Get total count
    count_result = await db.execute(
        select(func.count(Friendship.id)).where(
            Friendship.status == "accepted",
            or_(
                Friendship.requester_id == current_user.id,
                Friendship.addressee_id == current_user.id
            )
        )
    )
    total = count_result.scalar_one()

    return PaginatedFriends(
        items=friends,
        total=total,
        limit=limit,
        offset=offset
    )


@router.delete("/requests/{request_id}")
async def cancel_friend_request(
    request_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a sent friend request."""
    result = await db.execute(
        select(Friendship).where(
            Friendship.id == request_id,
            Friendship.requester_id == current_user.id,
            Friendship.status == "pending"
        )
    )
    friendship = result.scalar_one_or_none()

    if not friendship:
        raise HTTPException(status_code=404, detail="Friend request not found")

    await db.delete(friendship)
    await db.commit()

    return {"message": "Friend request cancelled"}


@router.delete("/{friend_id}")
async def remove_friend(
    friend_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a friend (delete the friendship)."""
    result = await db.execute(
        select(Friendship).where(
            Friendship.status == "accepted",
            or_(
                and_(Friendship.requester_id == current_user.id,
                     Friendship.addressee_id == friend_id),
                and_(Friendship.requester_id == friend_id,
                     Friendship.addressee_id == current_user.id)
            )
        )
    )
    friendship = result.scalar_one_or_none()

    if not friendship:
        raise HTTPException(status_code=404, detail="Friendship not found")

    await db.delete(friendship)
    await db.commit()

    return {"message": "Friend removed"}
