from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..services.jwt_service import JWTService
from ..models import User
from ..schemas import PrivacySettingsUpdate, PrivacySettingsResponse


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


