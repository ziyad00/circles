from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, desc, nullslast
from sqlalchemy.orm import aliased
from sqlalchemy.sql import expression as sql_expr
from typing import Optional

from ..database import get_db
from ..models import User, DMThread, DMMessage, DMParticipantState, DMMessageLike, DMMessageReaction, Follow
from ..config import settings
from ..services.storage import StorageService
from ..services.block_service import has_block_between
from ..services.websocket_service import WebSocketService
from ..schemas import (
    DMThreadResponse,
    PaginatedDMThreads,
    DMRequestCreate,
    DMRequestDecision,
    DMOpenCreate,
    DMMessageCreate,
    DMMessageResponse,
    PaginatedDMMessages,
    DMThreadStatus,
    DMThreadMuteUpdate,
    DMThreadPinUpdate,
    DMThreadArchiveUpdate,
    UnreadCountResponse,
    DMThreadBlockUpdate,
    TypingUpdate,
    TypingStatusResponse,
    PresenceResponse,
    HeartResponse,
    ReactionCreate,
    ReactionResponse,
    MessageForwardRequest,
    MessageSearchRequest,
    MessageSearchResponse,
    DeliveryStatusUpdate,
    VoiceMessageUploadResponse,
    FileUploadResponse,
    LocationShareRequest,
)
from ..services.jwt_service import JWTService
# from ..routers.users import _convert_single_to_signed_url  # Function removed in cleaned version

def _convert_single_to_signed_url(photo_url: str | None) -> str | None:
    """Convert a single storage key or S3 URL to a signed URL."""
    if not photo_url:
        return None

    import logging
    logger = logging.getLogger(__name__)
    logger.debug(f"Converting URL: {photo_url}, storage_backend: {settings.storage_backend}")

    if not photo_url.startswith("http"):
        if settings.storage_backend == "local":
            return f"{settings.local_base_url}{photo_url}"
        try:
            signed_url = StorageService.generate_signed_url(photo_url)
            logger.debug(f"Generated signed URL for key {photo_url}: {signed_url}")
            return signed_url
        except Exception as exc:
            logger.warning(f"Failed to sign photo URL {photo_url}: {exc}")
            return photo_url
    elif 's3.amazonaws.com' in photo_url or 'circles-media' in photo_url:
        try:
            if '/circles-media' in photo_url:
                s3_key = photo_url.split('/circles-media')[1].lstrip('/')
            elif '.s3.amazonaws.com/' in photo_url:
                s3_key = photo_url.split('.s3.amazonaws.com/')[1]
            else:
                return photo_url
            signed_url = StorageService.generate_signed_url(s3_key)
            logger.debug(f"Re-signed S3 URL {photo_url} -> {signed_url}")
            return signed_url
        except Exception as exc:
            logger.warning(f"Failed to re-sign S3 photo URL {photo_url}: {exc}")
            return photo_url
    else:
        return photo_url

router = APIRouter(
    prefix="/dms",
    tags=["direct messages"],
)

# ============================================================================
# DM INBOX ENDPOINT (Used by frontend)
# ============================================================================


@router.get("/inbox", response_model=PaginatedDMThreads)
async def get_inbox(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get user's DM inbox with pagination.

    **Authentication Required:** Yes
    """
    try:
        # Get threads where user is a participant
        query = select(DMThread).join(DMParticipantState).where(
            and_(
                DMParticipantState.user_id == current_user.id,
                DMParticipantState.blocked == False
            )
        ).order_by(desc(DMThread.updated_at))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        threads = result.scalars().all()

        # Convert to response format
        thread_responses = []
        for thread in threads:
            # Determine which user is the "other" user
            other_user_id = thread.user_b_id if thread.user_a_id == current_user.id else thread.user_a_id

            # Get other user details
            other_user_query = select(User).where(User.id == other_user_id)
            other_result = await db.execute(other_user_query)
            other_user = other_result.scalar_one_or_none()

            if other_user:
                thread_resp = DMThreadResponse(
                    id=thread.id,
                    user_a_id=thread.user_a_id,
                    user_b_id=thread.user_b_id,
                    initiator_id=thread.initiator_id,
                    status=thread.status,
                    created_at=thread.created_at,
                    updated_at=thread.updated_at,
                    other_user_name=other_user.name,
                    other_user_username=other_user.username,
                    other_user_avatar=_convert_single_to_signed_url(other_user.avatar_url),
                    last_message=None,  # TODO: Get last message
                    last_message_time=thread.updated_at,
                    is_muted=False,  # TODO: Get mute status
                    is_blocked=False,  # TODO: Get block status
                    sender_photo_url=None,  # TODO: Get last message sender photo
                )
                thread_responses.append(thread_resp)

        return PaginatedDMThreads(items=thread_responses, total=total, limit=limit, offset=offset)

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get inbox")

# ============================================================================
# DM MESSAGES ENDPOINTS (Used by frontend)
# ============================================================================


@router.get("/threads/{thread_id}/messages", response_model=PaginatedDMMessages)
async def get_thread_messages(
    thread_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Get messages from a specific thread.

    **Authentication Required:** Yes
    """
    try:
        # Verify user is participant in thread
        participant_query = select(DMParticipantState).where(
            and_(
                DMParticipantState.thread_id == thread_id,
                DMParticipantState.user_id == current_user.id,
                DMParticipantState.archived == False
            )
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            raise HTTPException(
                status_code=403, detail="Not a participant in this thread")

        # Get messages
        query = select(DMMessage).where(
            and_(
                DMMessage.thread_id == thread_id,
                or_(
                    DMMessage.deleted_by_user_id.is_(None),
                    DMMessage.deleted_by_user_id != current_user.id
                )
            )
        ).order_by(desc(DMMessage.created_at))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        messages = result.scalars().all()

        # Convert to response format
        message_responses = []
        for message in messages:
            # Get sender info
            sender_query = select(User).where(User.id == message.sender_id)
            sender_result = await db.execute(sender_query)
            sender = sender_result.scalar_one_or_none()

            if sender:
                message_resp = DMMessageResponse(
                    id=message.id,
                    thread_id=message.thread_id,
                    sender_id=message.sender_id,
                    sender_username=sender.username,
                    sender_display_name=sender.name,
                    sender_avatar_url=_convert_single_to_signed_url(sender.avatar_url),
                    text=message.text,
                    message_type=message.message_type,
                    photo_url=message.photo_urls,
                    created_at=message.created_at,
                    updated_at=message.created_at,  # Use created_at as fallback
                    is_edited=False,  # No edited field in schema
                    reply_to_id=message.reply_to_id,
                    is_forwarded=message.is_forwarded,
                    delivery_status=message.delivery_status,
                    delivered_at=message.delivered_at,
                )
                message_responses.append(message_resp)

        return PaginatedDMMessages(items=message_responses, total=total, limit=limit, offset=offset)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get messages")


@router.post("/threads/{thread_id}/messages", response_model=DMMessageResponse)
async def send_message(
    thread_id: int,
    message_data: DMMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Send a message to a thread.

    **Authentication Required:** Yes
    """
    try:
        # Verify user is participant in thread
        participant_query = select(DMParticipantState).where(
            and_(
                DMParticipantState.thread_id == thread_id,
                DMParticipantState.user_id == current_user.id,
                DMParticipantState.archived == False
            )
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            raise HTTPException(
                status_code=403, detail="Not a participant in this thread")

        # Create message
        message = DMMessage(
            thread_id=thread_id,
            sender_id=current_user.id,
            text=message_data.text,
            message_type=getattr(message_data, 'message_type', None) or "text",
            reply_to_id=getattr(message_data, 'reply_to_id', None),
            is_forwarded=getattr(message_data, 'is_forwarded', False),
        )

        db.add(message)
        await db.flush()  # Get the ID

        # Update thread timestamp
        thread_query = select(DMThread).where(DMThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if thread:
            thread.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(message)

        # Create response
        message_resp = DMMessageResponse(
            id=message.id,
            thread_id=message.thread_id,
            sender_id=message.sender_id,
            sender_username=current_user.username,
            sender_display_name=current_user.name,
            sender_avatar_url=_convert_single_to_signed_url(current_user.avatar_url),
            text=message.text,
            message_type=message.message_type,
            photo_url=message.photo_urls[0] if message.photo_urls else None,
            created_at=message.created_at,
            updated_at=message.created_at,  # Use created_at since updated_at doesn't exist
            is_edited=False,  # Can't determine without updated_at field
            reply_to_id=message.reply_to_id,
            is_forwarded=message.is_forwarded,
            delivery_status=message.delivery_status,
            delivered_at=message.delivered_at,
        )

        return message_resp

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import logging
        logging.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")

# ============================================================================
# DM OPEN ENDPOINT (Used by frontend)
# ============================================================================


@router.post("/open", response_model=DMThreadResponse)
async def open_dm(
    request: DMOpenCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Open or create a DM thread with another user.

    **Authentication Required:** Yes
    """
    try:
        # Validate other user
        if request.other_user_id == current_user.id:
            raise HTTPException(
                status_code=400, detail="Cannot open chat with yourself")

        other_user_query = select(User).where(User.id == request.other_user_id)
        other_user_result = await db.execute(other_user_query)
        other_user = other_user_result.scalar_one_or_none()

        if not other_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if users can chat (not blocked)
        if await has_block_between(db, current_user.id, request.other_user_id):
            raise HTTPException(
                status_code=403, detail="Cannot chat with this user")

        # Check if thread already exists
        participant_1 = aliased(DMParticipantState)
        participant_2 = aliased(DMParticipantState)

        existing_thread_query = select(DMThread).join(
            participant_1, DMThread.id == participant_1.thread_id
        ).join(
            participant_2, DMThread.id == participant_2.thread_id
        ).where(
            and_(
                participant_1.user_id == current_user.id,
                participant_1.archived == False,
                participant_2.user_id == request.other_user_id,
                participant_2.archived == False
            )
        )

        existing_result = await db.execute(existing_thread_query)
        existing_thread = existing_result.scalar_one_or_none()

        if existing_thread:
            # Return existing thread
            thread_resp = DMThreadResponse(
                id=existing_thread.id,
                user_a_id=existing_thread.user_a_id,
                user_b_id=existing_thread.user_b_id,
                initiator_id=existing_thread.initiator_id,
                status=existing_thread.status,
                created_at=existing_thread.created_at,
                updated_at=existing_thread.updated_at,
                other_user_name=other_user.name,
                other_user_username=other_user.username,
                other_user_avatar=_convert_single_to_signed_url(other_user.avatar_url),
                last_message=None,
                last_message_time=existing_thread.updated_at,
                is_muted=False,
                is_blocked=False,
            )
            return thread_resp

        # Create new thread with auto-acceptance
        thread = DMThread(
            user_a_id=current_user.id,
            user_b_id=request.other_user_id,
            initiator_id=current_user.id,
            status="accepted"
        )
        db.add(thread)
        await db.flush()  # Get the ID

        # Add participants
        current_user_participant = DMParticipantState(
            thread_id=thread.id,
            user_id=current_user.id,
            archived=False
        )
        other_user_participant = DMParticipantState(
            thread_id=thread.id,
            user_id=request.other_user_id,
            archived=False
        )

        db.add(current_user_participant)
        db.add(other_user_participant)

        await db.commit()
        await db.refresh(thread)

        # Create response
        thread_resp = DMThreadResponse(
            id=thread.id,
            user_a_id=thread.user_a_id,
            user_b_id=thread.user_b_id,
            initiator_id=thread.initiator_id,
            status=thread.status,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            other_user_name=other_user.name,
            other_user_username=other_user.username,
            other_user_avatar=_convert_single_to_signed_url(other_user.avatar_url),
            last_message=None,
            last_message_time=thread.created_at,
            is_muted=False,
            is_blocked=False,
        )

        return thread_resp

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import logging
        logging.error(f"Error opening DM: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to open DM: {str(e)}")


@router.post("/messages/{message_id}/like", status_code=status.HTTP_201_CREATED)
async def like_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Like/heart a DM message.

    **Authentication Required:** Yes
    """
    try:
        # Verify message exists and user has access
        message_query = select(DMMessage).where(DMMessage.id == message_id)
        message_result = await db.execute(message_query)
        message = message_result.scalar_one_or_none()

        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Verify user is part of the thread
        participant_query = select(DMParticipantState).where(
            DMParticipantState.thread_id == message.thread_id,
            DMParticipantState.user_id == current_user.id
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            raise HTTPException(status_code=403, detail="You are not part of this conversation")

        # Check if already liked
        existing_like_query = select(DMMessageLike).where(
            DMMessageLike.message_id == message_id,
            DMMessageLike.user_id == current_user.id
        )
        existing_like_result = await db.execute(existing_like_query)
        existing_like = existing_like_result.scalar_one_or_none()

        if existing_like:
            raise HTTPException(status_code=409, detail="Message already liked")

        # Create like
        like = DMMessageLike(
            message_id=message_id,
            user_id=current_user.id
        )
        db.add(like)
        await db.commit()

        return {"message": "Message liked successfully"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        import logging
        logging.error(f"Error liking message {message_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to like message: {str(e)}")


@router.delete("/messages/{message_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def unlike_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Unlike/unheart a DM message.

    **Authentication Required:** Yes
    """
    try:
        # Verify message exists and user has access
        message_query = select(DMMessage).where(DMMessage.id == message_id)
        message_result = await db.execute(message_query)
        message = message_result.scalar_one_or_none()

        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Verify user is part of the thread
        participant_query = select(DMParticipantState).where(
            DMParticipantState.thread_id == message.thread_id,
            DMParticipantState.user_id == current_user.id
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            raise HTTPException(status_code=403, detail="You are not part of this conversation")

        # Find and delete like
        like_query = select(DMMessageLike).where(
            DMMessageLike.message_id == message_id,
            DMMessageLike.user_id == current_user.id
        )
        like_result = await db.execute(like_query)
        like = like_result.scalar_one_or_none()

        if not like:
            raise HTTPException(status_code=404, detail="Like not found")

        await db.delete(like)
        await db.commit()

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        import logging
        logging.error(f"Error unliking message {message_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to unlike message: {str(e)}")


@router.get("/threads/{thread_id}/unread-count", response_model=dict)
async def get_thread_unread_count(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user)
):
    """Get unread message count for a specific thread."""
    try:
        # Check if user is participant in thread
        participant_query = select(DMParticipantState).where(
            DMParticipantState.thread_id == thread_id,
            DMParticipantState.user_id == current_user.id
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            raise HTTPException(status_code=403, detail="You are not part of this conversation")

        # Count unread messages (messages created after last_read_at)
        from datetime import datetime
        unread_query = select(func.count(DMMessage.id)).where(
            DMMessage.thread_id == thread_id,
            DMMessage.created_at > (participant.last_read_at or datetime.min)
        )
        unread_result = await db.execute(unread_query)
        unread_count = unread_result.scalar() or 0

        return {"unread_count": unread_count}

    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error getting unread count for thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get unread count: {str(e)}")


@router.post("/threads/{thread_id}/accept", response_model=dict)
async def accept_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(JWTService.get_current_user)
):
    """Accept a DM thread request."""
    try:
        # Get the thread
        thread_query = select(DMThread).where(DMThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Check if current user is participant
        if current_user.id not in (thread.user_a_id, thread.user_b_id):
            raise HTTPException(status_code=403, detail="You are not part of this conversation")

        # Only allow accepting if status is pending
        if thread.status != "pending":
            raise HTTPException(status_code=400, detail=f"Thread status is {thread.status}, not pending")

        # Accept the thread
        thread.status = "accepted"
        await db.commit()

        return {"message": "Thread accepted successfully", "status": "accepted"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        import logging
        logging.error(f"Error accepting thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to accept thread: {str(e)}")
