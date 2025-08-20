from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from ..database import get_db
from ..models import User, Follow
from ..services.jwt_service import JWTService
from ..schemas import PaginatedFollowers, PaginatedFollowing, FollowUserResponse
from ..routers.activity import create_follow_activity


router = APIRouter(prefix="/follow", tags=["follow"])


@router.post("/{user_id}")
async def follow_user(user_id: int, current_user: User = Depends(JWTService.get_current_user), db: AsyncSession = Depends(get_db)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
    res = await db.execute(select(User).where(User.id == user_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    res = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == user_id))
    if res.scalars().first():
        return {"message": "already following"}
    db.add(Follow(follower_id=current_user.id, followee_id=user_id))
    await db.commit()
    
    # Create activity for the follow
    try:
        await create_follow_activity(
            db=db,
            follower_id=current_user.id,
            followee_id=user_id,
            followee_name=target.name or target.email
        )
    except Exception as e:
        # Log error but don't fail the follow creation
        print(f"Failed to create activity for follow {current_user.id} -> {user_id}: {e}")
    
    return {"message": "ok"}


@router.delete("/{user_id}")
async def unfollow_user(user_id: int, current_user: User = Depends(JWTService.get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == user_id))
    row = res.scalars().first()
    if not row:
        return {"message": "not following"}
    await db.delete(row)
    await db.commit()
    return {"message": "ok"}


@router.get("/followers", response_model=PaginatedFollowers)
async def list_followers(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), current_user: User = Depends(JWTService.get_current_user), db: AsyncSession = Depends(get_db)):
    subq = select(Follow).where(
        Follow.followee_id == current_user.id).subquery()
    total = (await db.execute(select(func.count()).select_from(subq))).scalar_one()
    res = await db.execute(
        select(User, subq.c.created_at).join_from(User, subq, User.id == subq.c.follower_id).order_by(
            desc(subq.c.created_at)).offset(offset).limit(limit)
    )
    items = [FollowUserResponse(id=u.id, email=u.email, is_verified=u.is_verified,
                                created_at=u.created_at, followed_at=created_at) for (u, created_at) in res.all()]
    return PaginatedFollowers(items=items, total=total, limit=limit, offset=offset)


@router.get("/following", response_model=PaginatedFollowing)
async def list_following(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), current_user: User = Depends(JWTService.get_current_user), db: AsyncSession = Depends(get_db)):
    subq = select(Follow).where(
        Follow.follower_id == current_user.id).subquery()
    total = (await db.execute(select(func.count()).select_from(subq))).scalar_one()
    res = await db.execute(
        select(User, subq.c.created_at).join_from(User, subq, User.id == subq.c.followee_id).order_by(
            desc(subq.c.created_at)).offset(offset).limit(limit)
    )
    items = [FollowUserResponse(id=u.id, email=u.email, is_verified=u.is_verified,
                                created_at=u.created_at, followed_at=created_at) for (u, created_at) in res.all()]
    return PaginatedFollowing(items=items, total=total, limit=limit, offset=offset)
