from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..services.jwt_service import JWTService
from ..models import User, NotificationPreference
from ..schemas import PrivacySettingsUpdate, PrivacySettingsResponse, NotificationPreferencesUpdate, NotificationPreferencesResponse


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/privacy", response_model=PrivacySettingsResponse)
async def get_privacy_settings(
    current_user: User = Depends(JWTService.get_current_user),
):
    return PrivacySettingsResponse(
        dm_privacy=current_user.dm_privacy,
        checkins_default_visibility=current_user.checkins_default_visibility,
        collections_default_visibility=current_user.collections_default_visibility,
    )


@router.put("/privacy", response_model=PrivacySettingsResponse)
async def update_privacy_settings(
    payload: PrivacySettingsUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.dm_privacy is not None:
        current_user.dm_privacy = payload.dm_privacy
    if payload.checkins_default_visibility is not None:
        current_user.checkins_default_visibility = payload.checkins_default_visibility
    if payload.collections_default_visibility is not None:
        current_user.collections_default_visibility = payload.collections_default_visibility
    await db.commit()
    await db.refresh(current_user)
    return PrivacySettingsResponse(
        dm_privacy=current_user.dm_privacy,
        checkins_default_visibility=current_user.checkins_default_visibility,
        collections_default_visibility=current_user.collections_default_visibility,
    )


async def _get_or_create_prefs(db: AsyncSession, user_id: int) -> NotificationPreference:
    res = await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
    prefs = res.scalars().first()
    if not prefs:
        prefs = NotificationPreference(user_id=user_id)
        db.add(prefs)
        await db.commit()
        await db.refresh(prefs)
    return prefs


@router.get("/notifications", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await _get_or_create_prefs(db, current_user.id)
    return NotificationPreferencesResponse(
        dm_messages=prefs.dm_messages,
        dm_requests=prefs.dm_requests,
        follows=prefs.follows,
        likes=prefs.likes,
        comments=prefs.comments,
        activity_summary=prefs.activity_summary,
        marketing=prefs.marketing,
    )


@router.put("/notifications", response_model=NotificationPreferencesResponse)
async def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await _get_or_create_prefs(db, current_user.id)
    for field in [
        "dm_messages",
        "dm_requests",
        "follows",
        "likes",
        "comments",
        "activity_summary",
        "marketing",
    ]:
        val = getattr(payload, field)
        if val is not None:
            setattr(prefs, field, val)
    await db.commit()
    await db.refresh(prefs)
    return NotificationPreferencesResponse(
        dm_messages=prefs.dm_messages,
        dm_requests=prefs.dm_requests,
        follows=prefs.follows,
        likes=prefs.likes,
        comments=prefs.comments,
        activity_summary=prefs.activity_summary,
        marketing=prefs.marketing,
    )
