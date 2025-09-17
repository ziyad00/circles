from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..config import settings
from ..models import User, CheckIn, Place, DMThread, DMMessage
from ..services.block_service import has_block_between


async def create_private_reply_from_place_chat(
    db: AsyncSession,
    place_id: int,
    sender_id: int,
    target_user_id: int,
    message_text: str,
    context_text: Optional[str] = None,
) -> Tuple[DMThread, DMMessage, Optional[Place]]:
    """Create a DM message as a private reply from a place chat."""

    if target_user_id == sender_id:
        raise HTTPException(status_code=400, detail="Cannot message yourself")

    message_text = (message_text or "").strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message text required")

    target_res = await db.execute(select(User).where(User.id == target_user_id))
    target_user = target_res.scalars().first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    window_cutoff = datetime.now(timezone.utc) - \
        timedelta(hours=int(settings.place_chat_window_hours))

    participation_query = select(CheckIn).where(
        CheckIn.user_id == target_user_id,
        CheckIn.place_id == place_id,
        CheckIn.created_at >= window_cutoff,
    )
    if not (await db.execute(participation_query)).scalar_one_or_none():
        raise HTTPException(
            status_code=403,
            detail="User is no longer active in this place chat",
        )

    if await has_block_between(db, sender_id, target_user_id):
        raise HTTPException(
            status_code=403,
            detail="You cannot message this user right now",
        )

    a, b = (sender_id, target_user_id)
    if a > b:
        a, b = b, a

    thread_res = await db.execute(
        select(DMThread).where(
            DMThread.user_a_id == a,
            DMThread.user_b_id == b,
        )
    )
    thread = thread_res.scalars().first()
    if not thread:
        thread = DMThread(
            user_a_id=a,
            user_b_id=b,
            initiator_id=sender_id,
            status="accepted",
        )
        db.add(thread)
        await db.flush()

    place_res = await db.execute(select(Place).where(Place.id == place_id))
    place = place_res.scalars().first()

    prefix_lines: list[str] = []
    if place:
        prefix_lines.append(f"[Private reply from place chat: {place.name}]")
    else:
        prefix_lines.append("[Private reply from place chat]")

    context_text = (context_text or "").strip()
    if context_text:
        snippet = context_text[:200]
        if len(context_text) > 200:
            snippet += "..."
        prefix_lines.append(f"> {snippet}")

    dm_body = "\n".join(prefix_lines + ["", message_text]) if prefix_lines else message_text

    dm_message = DMMessage(
        thread_id=thread.id,
        sender_id=sender_id,
        text=dm_body,
    )
    db.add(dm_message)
    thread.updated_at = func.now()

    await db.commit()
    await db.refresh(dm_message)

    return thread, dm_message, place
