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
        # Legacy settings (backward compatibility)
        dm_privacy=current_user.dm_privacy,
        checkins_default_visibility=current_user.checkins_default_visibility,
        collections_default_visibility=current_user.collections_default_visibility,
        # Comprehensive privacy controls
        profile_visibility=getattr(current_user, 'profile_visibility', 'public'),
        follower_list_visibility=getattr(current_user, 'follower_list_visibility', 'public'),
        following_list_visibility=getattr(current_user, 'following_list_visibility', 'public'),
        stats_visibility=getattr(current_user, 'stats_visibility', 'public'),
        media_default_visibility=getattr(current_user, 'media_default_visibility', 'public'),
        search_visibility=getattr(current_user, 'search_visibility', 'public'),
    )


@router.put("/privacy", response_model=PrivacySettingsResponse)
async def update_privacy_settings(
    payload: PrivacySettingsUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Legacy settings (backward compatibility)
    if payload.dm_privacy is not None:
        current_user.dm_privacy = payload.dm_privacy
    if payload.checkins_default_visibility is not None:
        current_user.checkins_default_visibility = payload.checkins_default_visibility
    if payload.collections_default_visibility is not None:
        current_user.collections_default_visibility = payload.collections_default_visibility

    # Comprehensive privacy controls
    if payload.profile_visibility is not None:
        current_user.profile_visibility = payload.profile_visibility.value
    if payload.follower_list_visibility is not None:
        current_user.follower_list_visibility = payload.follower_list_visibility.value
    if payload.following_list_visibility is not None:
        current_user.following_list_visibility = payload.following_list_visibility.value
    if payload.stats_visibility is not None:
        current_user.stats_visibility = payload.stats_visibility.value
    if payload.media_default_visibility is not None:
        current_user.media_default_visibility = payload.media_default_visibility.value
    if payload.search_visibility is not None:
        current_user.search_visibility = payload.search_visibility.value

    await db.commit()
    await db.refresh(current_user)
    return PrivacySettingsResponse(
        # Legacy settings
        dm_privacy=current_user.dm_privacy,
        checkins_default_visibility=current_user.checkins_default_visibility,
        collections_default_visibility=current_user.collections_default_visibility,
        # Comprehensive privacy controls
        profile_visibility=current_user.profile_visibility,
        follower_list_visibility=current_user.follower_list_visibility,
        following_list_visibility=current_user.following_list_visibility,
        stats_visibility=current_user.stats_visibility,
        media_default_visibility=current_user.media_default_visibility,
        search_visibility=current_user.search_visibility,
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
