from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..services.jwt_service import JWTService
from ..services.storage import StorageService
from ..models import User, CheckIn, CheckInPhoto, Photo, Follow, UserInterest, CheckInCollection
from ..schemas import (
    UserUpdate,
    PublicUserResponse,
    InterestCreate,
    InterestResponse,
    PaginatedCheckIns,
    CheckInResponse,
    PaginatedMedia,
)


router = APIRouter(prefix="/users", tags=["users"])
@router.get("/search", response_model=list[PublicUserResponse])
async def search_users(q: str, limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.email.ilike(f"%{q}%") | User.name.ilike(f"%{q}%")).limit(limit)
    return (await db.execute(stmt)).scalars().all()



@router.get("/{user_id}", response_model=PublicUserResponse)
async def get_user_profile(user_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/me", response_model=PublicUserResponse)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.name is not None:
        current_user.name = payload.name
    if payload.bio is not None:
        current_user.bio = payload.bio
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/me/avatar", response_model=PublicUserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import os
    from uuid import uuid4
    _, ext = os.path.splitext(file.filename or "")
    if not ext:
        ext = ".jpg"
    filename = f"{uuid4().hex}{ext}"
    content = await file.read()
    # reuse check-in storage pattern for avatars
    # store under media/avatars/{user_id}/
    if hasattr(StorageService, "_save_checkin_local"):
        # quick local path
        media_root = os.path.abspath(os.path.join(os.getcwd(), "media"))
        target_dir = os.path.join(media_root, "avatars", str(current_user.id))
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)
        with open(target_path, "wb") as f:
            f.write(content)
        url_path = f"/media/avatars/{current_user.id}/{filename}"
    else:
        url_path = await StorageService._save_checkin_s3(current_user.id, filename, content)
    current_user.avatar_url = url_path
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/{user_id}/check-ins", response_model=PaginatedCheckIns)
async def list_user_checkins(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    # visibility enforcement: reuse can_view_checkin-like logic
    from ..utils import can_view_checkin
    total_res = await db.execute(select(func.count(CheckIn.id)).where(CheckIn.user_id == user_id))
    total = total_res.scalar_one()
    res = await db.execute(
        select(CheckIn)
        .where(CheckIn.user_id == user_id)
        .order_by(CheckIn.created_at.desc())
        .offset(offset)
        .limit(limit * 2)
    )
    rows = res.scalars().all()
    visible = []
    for ci in rows:
        if await can_view_checkin(db, ci.user_id, current_user.id, ci.visibility):
            visible.append(ci)
            if len(visible) >= limit:
                break
    # hydrate photo_urls
    result: list[CheckInResponse] = []
    for ci in visible:
        res_ph = await db.execute(select(CheckInPhoto).where(CheckInPhoto.check_in_id == ci.id).order_by(CheckInPhoto.created_at.asc()))
        urls = [p.url for p in res_ph.scalars().all()]
        result.append(
            CheckInResponse(
                id=ci.id,
                user_id=ci.user_id,
                place_id=ci.place_id,
                note=ci.note,
                visibility=ci.visibility,
                created_at=ci.created_at,
                expires_at=ci.expires_at,
                photo_url=ci.photo_url,
                photo_urls=urls,
            )
        )
    return PaginatedCheckIns(items=result, total=total, limit=limit, offset=offset)


@router.get("/{user_id}/media", response_model=PaginatedMedia)
async def list_user_media(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    # collect review photos and check-in photos with visibility checks
    from ..utils import can_view_checkin
    # review photos: always public for now (attached to reviews)
    total_photos = (await db.execute(select(func.count(Photo.id)).where(Photo.user_id == user_id, Photo.review_id.is_not(None)))).scalar_one()
    res_photos = await db.execute(
        select(Photo.url).where(Photo.user_id == user_id, Photo.review_id.is_not(None)).order_by(Photo.created_at.desc()).offset(offset).limit(limit)
    )
    urls = [u[0] for u in res_photos.all()]
    # check-in photos: filter via check-in visibility
    res_ci = await db.execute(
        select(CheckIn.id, CheckIn.visibility).where(CheckIn.user_id == user_id).order_by(CheckIn.created_at.desc()).offset(0).limit(limit * 3)
    )
    ci_rows = res_ci.all()
    ci_ids = [row[0] for row in ci_rows]
    if ci_ids:
        res_cips = await db.execute(select(CheckInPhoto).where(CheckInPhoto.check_in_id.in_(ci_ids)).order_by(CheckInPhoto.created_at.desc()))
        cip_list = res_cips.scalars().all()
        # map check_in_id -> visibility
        vis_map = {row[0]: row[1] for row in ci_rows}
        for cip in cip_list:
            vis = vis_map.get(cip.check_in_id, "public")
            if await can_view_checkin(db, user_id, current_user.id, vis):
                urls.append(cip.url)
                if len(urls) >= limit:
                    break
    total = total_photos  # approximate; not counting CI photos separately here
    items = urls[:limit]
    return PaginatedMedia(items=items, total=total, limit=limit, offset=offset)


@router.get("/{user_id}/collections", response_model=list[dict])
async def list_user_collections(
    user_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Owner gets all; others get public or friends (followers-only)
    base = select(CheckInCollection).where(CheckInCollection.user_id == user_id)
    if current_user.id != user_id:
        from ..models import Follow
        is_follower = (await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == user_id))).scalars().first() is not None
        if is_follower:
            base = base.where(CheckInCollection.visibility.in_(["public", "friends"]))
        else:
            base = base.where(CheckInCollection.visibility == "public")
    res = await db.execute(base.order_by(CheckInCollection.created_at.desc()))
    cols = res.scalars().all()
    # return minimal fields
    return [{"id": c.id, "name": c.name, "visibility": c.visibility, "created_at": c.created_at} for c in cols]


@router.get("/me/interests", response_model=list[InterestResponse])
async def my_interests(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(UserInterest).where(UserInterest.user_id == current_user.id).order_by(UserInterest.created_at.desc()))
    return res.scalars().all()


@router.post("/me/interests", response_model=InterestResponse)
async def add_interest(
    payload: InterestCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # simple upsert avoid dupes
    exists = await db.execute(select(UserInterest).where(UserInterest.user_id == current_user.id, UserInterest.name == payload.name))
    if exists.scalars().first():
        raise HTTPException(status_code=400, detail="Interest already exists")
    it = UserInterest(user_id=current_user.id, name=payload.name)
    db.add(it)
    await db.commit()
    await db.refresh(it)
    return it


@router.delete("/me/interests/{interest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_interest(
    interest_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(UserInterest).where(UserInterest.id == interest_id, UserInterest.user_id == current_user.id))
    it = res.scalars().first()
    if not it:
        raise HTTPException(status_code=404, detail="Interest not found")
    await db.delete(it)
    await db.commit()
    return None


