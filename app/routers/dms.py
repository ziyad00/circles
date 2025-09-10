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
from ..services.websocket_service import WebSocketService
from ..schemas import (
    DMThreadResponse,
    PaginatedDMThreads,
    DMRequestCreate,
    DMRequestDecision,
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
)
from ..services.jwt_service import JWTService
from ..routers.users import _convert_single_to_signed_url


router = APIRouter(
    prefix="/dms",
    tags=["direct messages"],
    responses={
        404: {"description": "Thread or message not found"},
        400: {"description": "Invalid request data"},
        403: {"description": "Access denied or privacy restriction"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"}
    }
)

# Rate limiting storage
# user_id -> list of timestamps
_dm_request_log: dict[int, list[datetime]] = {}
# user_id -> list of timestamps
_dm_message_log: dict[int, list[datetime]] = {}

# Rate limits
DM_REQUEST_LIMIT = settings.dm_requests_per_min
DM_MESSAGE_LIMIT = settings.dm_messages_per_min


def _check_rate_limit(user_id: int, log_dict: dict, limit: int, window_minutes: int = 1):
    """Check if user has exceeded rate limit"""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)

    if user_id not in log_dict:
        log_dict[user_id] = []

    # Remove old entries outside the window
    log_dict[user_id] = [ts for ts in log_dict[user_id] if ts > window_start]

    # Check if limit exceeded
    if len(log_dict[user_id]) >= limit:
        return False

    # Add current request
    log_dict[user_id].append(now)
    return True


def _normalize_pair(user_id: int, other_id: int) -> tuple[int, int]:
    return (user_id, other_id) if user_id < other_id else (other_id, user_id)


@router.post("/requests", response_model=DMThreadResponse)
async def send_dm_request(
    payload: DMRequestCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a DM request to start a conversation.

    **Authentication Required:** Yes

    **Privacy Controls:**
    - Respects recipient's DM privacy settings
    - `everyone`: Anyone can send requests
    - `followers`: Only followers can send requests
    - `no_one`: No one can send requests

    **Rate Limiting:**
    - 5 requests per minute per user
    - Prevents spam and harassment

    **Request Flow:**
    1. Request is sent to recipient
    2. Recipient can accept/reject via `/dms/requests`
    3. If accepted, thread becomes active
    4. Messages can then be sent normally

    **Use Cases:**
    - Start conversations with new users
    - Respect privacy boundaries
    - Prevent unwanted messages
    - Social networking features
    """
    # Rate limiting
    if not _check_rate_limit(current_user.id, _dm_request_log, DM_REQUEST_LIMIT):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {DM_REQUEST_LIMIT} DM requests per minute."
        )

    # Guard: cannot message self
    if payload.recipient_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot message yourself")
    # find recipient by id
    res = await db.execute(select(User).where(User.id == payload.recipient_id))
    recipient = res.scalars().first()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    # Enforce recipient privacy unless direct DMs are globally allowed
    # everyone | followers | no_one
    dm_priv = recipient.dm_privacy or "everyone"
    if not settings.dm_allow_direct:
        if dm_priv == "no_one":
            raise HTTPException(
                status_code=403, detail="Recipient does not accept DMs")
        if dm_priv == "followers":
            resf = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == recipient.id))
            if resf.scalars().first() is None:
                raise HTTPException(
                    status_code=403, detail="Recipient accepts DMs from followers only")

    # Check if recipient has blocked the sender
    from ..models import DMParticipantState
    block_check = await db.execute(
        select(DMParticipantState).where(
            DMParticipantState.user_id == recipient.id,
            DMParticipantState.thread_id.in_(
                select(DMThread.id).where(
                    or_(
                        and_(DMThread.user_a_id == current_user.id,
                             DMThread.user_b_id == recipient.id),
                        and_(DMThread.user_a_id == recipient.id,
                             DMThread.user_b_id == current_user.id)
                    )
                )
            ),
            DMParticipantState.blocked == True
        )
    )
    if block_check.scalar_one_or_none():
        raise HTTPException(
            status_code=403, detail="Cannot send DM request to user who has blocked you")

    a, b = _normalize_pair(current_user.id, recipient.id)
    # Determine auto-accept policy
    res_follow = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == recipient.id))
    follows = res_follow.scalars().first()
    # existing thread
    res = await db.execute(select(DMThread).where(DMThread.user_a_id == a, DMThread.user_b_id == b))
    thread = res.scalars().first()
    if not thread:
        auto = settings.dm_allow_direct or (
            bool(follows) and (dm_priv in ("everyone", "followers")))
        thread = DMThread(user_a_id=a, user_b_id=b,
                          initiator_id=current_user.id, status=("accepted" if auto else "pending"))
        db.add(thread)
        await db.flush()
    # if accepted (follower), create initial message; if pending, store as request note (message) too
    msg = DMMessage(thread_id=thread.id,
                    sender_id=current_user.id, text=payload.text)
    db.add(msg)
    await db.commit()
    await db.refresh(thread)

    # Send DM request notification if status is pending (still possible when allow_direct is False)
    if thread.status == "pending":
        try:
            await WebSocketService.send_dm_request_notification(
                recipient.id,
                {
                    "sender_id": current_user.id,
                    "sender_name": current_user.name,
                    "sender_username": current_user.username,
                    "thread_id": thread.id,
                    "message_text": payload.text[:100] + ("..." if len(payload.text) > 100 else ""),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        except Exception as e:
            print(f"Failed to send DM request notification: {e}")

    return thread


@router.get("/requests", response_model=PaginatedDMThreads)
async def list_dm_requests(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    # requests where user participates AND status pending AND user is not initiator
    base = select(DMThread).where(
        DMThread.status == "pending",
        or_(DMThread.user_a_id == current_user.id,
            DMThread.user_b_id == current_user.id),
        DMThread.initiator_id != current_user.id,
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    stmt = base.order_by(desc(DMThread.updated_at)).offset(offset).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
    return PaginatedDMThreads(items=items, total=total, limit=limit, offset=offset)


@router.put("/requests/{thread_id}", response_model=DMThreadResponse)
async def respond_dm_request(
    thread_id: int,
    payload: DMRequestDecision,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if current_user.id not in (thread.user_a_id, thread.user_b_id):
        raise HTTPException(status_code=403, detail="Not allowed")
    if thread.initiator_id == current_user.id:
        raise HTTPException(
            status_code=400, detail="Initiator cannot decide their own request")
    if payload.status not in (DMThreadStatus.accepted, DMThreadStatus.rejected):
        raise HTTPException(status_code=400, detail="Invalid status")
    thread.status = payload.status
    await db.commit()
    await db.refresh(thread)
    return thread


@router.get("/inbox", response_model=PaginatedDMThreads)
async def inbox(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(
        None, description="Search query for messages or participant names"),
    include_archived: bool = Query(
        False, description="Include archived threads"),
    only_pinned: bool = Query(False, description="Only show pinned threads"),
):
    """
    Get user's DM inbox with advanced filtering.

    **Authentication Required:** Yes

    **Features:**
    - Shows all active DM threads
    - Advanced search and filtering
    - Pin and archive support
    - Unread message counts

    **Search & Filtering:**
    - `q`: Search in messages and participant names
    - `include_archived`: Show/hide archived threads
    - `only_pinned`: Show only pinned threads
    - `limit`/`offset`: Standard pagination

    **Thread Organization:**
    - Pinned threads appear first
    - Ordered by most recent activity
    - Unread counts included
    - Participant information

    **Use Cases:**
    - DM inbox interface
    - Thread management
    - Search conversations
    - Organize important threads
    """
    # Get other user's info and last message in one query
    other_user_id = sql_expr.case(
        (DMThread.user_a_id == current_user.id, DMThread.user_b_id),
        else_=DMThread.user_a_id,
    )

    # Subquery for last message with reply handling (decoupled from outer query)
    last_msg_ranked = (
        select(
            DMMessage.thread_id,
            DMMessage.text.label("last_message_text"),
            DMMessage.reply_to_text.label("reply_preview"),
            DMMessage.created_at.label("last_message_time"),
            DMMessage.sender_id.label("last_sender_id"),
            func.row_number().over(
                partition_by=DMMessage.thread_id,
                order_by=DMMessage.created_at.desc(),
            ).label("rn"),
        )
        .where(DMMessage.deleted_at.is_(None))
        .subquery()
    )
    last_msg_subq = select(last_msg_ranked).where(
        last_msg_ranked.c.rn == 1).subquery()

    sender_user = aliased(User)

    base = (
        select(
            DMThread,
            User.name.label("other_user_name"),
            User.username.label("other_user_username"),
            User.avatar_url.label("other_user_avatar"),
            DMParticipantState.muted.label("is_muted"),
            DMParticipantState.blocked.label("is_blocked"),
            last_msg_subq.c.last_message_text.label("last_message"),
            last_msg_subq.c.last_message_time.label("last_message_time"),
            last_msg_subq.c.reply_preview.label("reply_preview"),
            sender_user.avatar_url.label("sender_photo_url"),
        )
        .join(
            DMParticipantState,
            and_(
                DMParticipantState.thread_id == DMThread.id,
                DMParticipantState.user_id == current_user.id,
            ),
            isouter=True,
        )
        .join(
            User,
            User.id == other_user_id,
            isouter=True,
        )
        .join(
            last_msg_subq,
            and_(
                last_msg_subq.c.thread_id == DMThread.id,
            ),
            isouter=True,
        )
        # Join sender_user via self-join on users using last_sender_id
        .join(
            sender_user,
            sender_user.id == last_msg_subq.c.last_sender_id,
            isouter=True,
        )
        .where(
            DMThread.status == "accepted",
            or_(DMThread.user_a_id == current_user.id,
                DMThread.user_b_id == current_user.id),
        )
    )

    # archived filter
    if not include_archived:
        base = base.where(
            or_(DMParticipantState.archived.is_(False),
                DMParticipantState.archived.is_(None))
        )

    # pinned filter
    if only_pinned:
        base = base.where(DMParticipantState.pinned.is_(True))

    # search filter
    if q:
        like = f"%{q}%"
        base = base.where(
            or_(
                last_msg_subq.c.last_message_text.ilike(like),
                User.name.ilike(like),
                User.username.ilike(like)
            )
        )

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    # order: pinned first (treat NULL as false), then updated_at desc
    pinned_first = func.coalesce(DMParticipantState.pinned, False).desc()
    stmt = base.order_by(pinned_first, desc(
        DMThread.updated_at)).offset(offset).limit(limit)
    results = (await db.execute(stmt)).all()

    # Convert results to DMThreadResponse objects with additional fields
    items = []
    for result in results:
        thread = result[0]  # DMThread object
        other_user_name = result[1]
        other_user_username = result[2]
        other_user_avatar = result[3]
        is_muted = result[4]
        is_blocked = result[5]
        last_message = result[6]
        last_message_time = result[7]
        reply_preview = result[8]
        sender_photo_url = result[9] if len(result) > 9 else None

        # Handle reply preview in last message
        if reply_preview and last_message:
            # If it's a reply, show a shortened version
            last_message = last_message[:100] + \
                ("..." if len(last_message) > 100 else "")

        # Convert avatar URL to signed URL if needed
        if other_user_avatar and not other_user_avatar.startswith('http'):
            try:
                other_user_avatar = _convert_single_to_signed_url(
                    other_user_avatar)
            except Exception:
                pass  # Keep original if signing fails

        response_item = DMThreadResponse(
            id=thread.id,
            user_a_id=thread.user_a_id,
            user_b_id=thread.user_b_id,
            initiator_id=thread.initiator_id,
            status=thread.status,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            other_user_name=other_user_name,
            other_user_username=other_user_username,
            other_user_avatar=other_user_avatar,
            is_muted=bool(is_muted) if is_muted is not None else None,
            is_blocked=bool(is_blocked) if is_blocked is not None else None,
            last_message=last_message,
            last_message_time=last_message_time,
            sender_photo_url=sender_photo_url,
        )
        items.append(response_item)

    return PaginatedDMThreads(items=items, total=total, limit=limit, offset=offset)


def _is_participant(thread: DMThread, user_id: int) -> bool:
    return user_id in (thread.user_a_id, thread.user_b_id)


@router.get("/threads/{thread_id}/messages", response_model=PaginatedDMMessages)
async def list_messages(
    thread_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    base = select(DMMessage).where(
        DMMessage.thread_id == thread_id,
        DMMessage.deleted_at.is_(None)
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    stmt = base.order_by(DMMessage.created_at.asc()
                         ).offset(offset).limit(limit)
    messages = (await db.execute(stmt)).scalars().all()
    # compute 'seen' for messages sent by current_user
    other_id = thread.user_a_id if current_user.id == thread.user_b_id else thread.user_b_id
    res_other = await db.execute(select(DMParticipantState).where(_participant_state_base(thread_id, other_id)))
    other_state = res_other.scalars().first()
    other_last_read = other_state.last_read_at if other_state else None
    # get like counts and my likes
    msg_ids = [m.id for m in messages]
    like_counts = {}
    liked_by_me_set = set()
    if msg_ids:
        counts_rows = await db.execute(
            select(DMMessageLike.message_id, func.count(DMMessageLike.id)).where(
                DMMessageLike.message_id.in_(msg_ids)).group_by(DMMessageLike.message_id)
        )
        for mid, cnt in counts_rows.all():
            like_counts[mid] = cnt
        my_rows = await db.execute(
            select(DMMessageLike.message_id).where(DMMessageLike.message_id.in_(
                msg_ids), DMMessageLike.user_id == current_user.id)
        )
        liked_by_me_set = {r[0] for r in my_rows.all()}
    # Build response items explicitly to set seen + heart
    response_items = []
    for m in messages:
        seen = None
        if m.sender_id == current_user.id and other_last_read is not None:
            seen = m.created_at <= other_last_read

        # Get reply sender name if this is a reply
        reply_sender_name = None
        if m.reply_to_id and m.reply_to:
            reply_sender_name = m.reply_to.sender.name

        response_items.append(
            DMMessageResponse(
                id=m.id,
                thread_id=m.thread_id,
                sender_id=m.sender_id,
                text=m.text,
                created_at=m.created_at,
                seen=seen,
                heart_count=like_counts.get(m.id, 0),
                liked_by_me=(m.id in liked_by_me_set),
                reply_to_id=m.reply_to_id,
                reply_to_text=m.reply_to_text,
                reply_to_sender_name=reply_sender_name,
                photo_urls=m.photo_urls or [],
                video_urls=m.video_urls or [],
                caption=m.caption,
            )
        )
    return PaginatedDMMessages(items=response_items, total=total, limit=limit, offset=offset)


@router.post("/threads/{thread_id}/messages", response_model=DMMessageResponse)
async def send_message(
    thread_id: int,
    payload: DMMessageCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message in a DM thread.

    **Authentication Required:** Yes

    **Features:**
    - Send text messages in active threads
    - Rate limiting (20 messages per minute)
    - Automatic unread count updates
    - Real-time delivery via WebSocket

    **Rate Limiting:**
    - 20 messages per minute per user
    - Prevents spam and abuse

    **Message Lifecycle:**
    1. Message is saved to database
    2. Unread counts updated for other participants
    3. Real-time notification sent via WebSocket
    4. Message appears in thread history

    **Privacy:**
    - Only thread participants can send messages
    - Blocked users cannot send messages
    - Muted threads still allow sending

    **Use Cases:**
    - Private conversations
    - Real-time messaging
    - Social interactions
    - Privacy-controlled communication
    """
    # Rate limiting
    if not _check_rate_limit(current_user.id, _dm_message_log, DM_MESSAGE_LIMIT):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {DM_MESSAGE_LIMIT} messages per minute."
        )

    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    if thread.status != "accepted":
        raise HTTPException(status_code=400, detail="Thread not accepted")
    # prevent sending if the other participant has blocked current user
    other_id = thread.user_a_id if current_user.id == thread.user_b_id else thread.user_b_id
    other_state = await _get_or_create_state(db, thread_id, other_id)
    if other_state and getattr(other_state, "blocked", False):
        raise HTTPException(
            status_code=403, detail="You are blocked by this user")

    # Handle reply functionality
    reply_to_text = None
    if payload.reply_to_id:
        # Validate the reply_to_id exists and is in the same thread
        reply_msg_result = await db.execute(
            select(DMMessage).where(
                DMMessage.id == payload.reply_to_id,
                DMMessage.thread_id == thread_id,
                DMMessage.deleted_at.is_(None)
            )
        )
        reply_msg = reply_msg_result.scalars().first()
        if not reply_msg:
            raise HTTPException(
                status_code=400,
                detail="Reply message not found or not in this thread"
            )
        # Store preview text of the message being replied to
        if reply_msg.text.strip():
            reply_to_text = reply_msg.text[:200] + \
                "..." if len(reply_msg.text) > 200 else reply_msg.text
        elif reply_msg.photo_urls:
            reply_to_text = f"[Photo] {reply_msg.caption or ''}".strip()
        elif reply_msg.video_urls:
            reply_to_text = f"[Video] {reply_msg.caption or ''}".strip()
        else:
            reply_to_text = "[Media message]"

    msg = DMMessage(
        thread_id=thread_id,
        sender_id=current_user.id,
        text=payload.text,
        reply_to_id=payload.reply_to_id,
        reply_to_text=reply_to_text,
        photo_urls=payload.photo_urls,
        video_urls=payload.video_urls,
        caption=payload.caption
    )
    db.add(msg)
    # bump thread updated_at
    thread.updated_at = func.now()
    await db.commit()
    await db.refresh(msg)

    # Get reply sender name if this is a reply
    reply_sender_name = None
    if msg.reply_to_id and msg.reply_to:
        reply_sender_name = msg.reply_to.sender.name

    # Send real-time notifications
    try:
        # Get the other participant
        other_user_id = thread.user_a_id if thread.user_b_id == current_user.id else thread.user_b_id

        # Check if the recipient has muted this thread
        participant_state_result = await db.execute(
            select(DMParticipantState).where(
                DMParticipantState.thread_id == thread_id,
                DMParticipantState.user_id == other_user_id
            )
        )
        participant_state = participant_state_result.scalars().first()

        # Only send notification if not muted
        if not participant_state or not participant_state.muted:
            # Prepare notification data
            notification_data = {
                "sender_id": current_user.id,
                "sender_name": current_user.name,
                "sender_username": current_user.username,
                "thread_id": thread_id,
                "message_id": msg.id,
                "message_text": msg.text[:100] + ("..." if len(msg.text) > 100 else ""),
                "has_media": bool(msg.photo_urls or msg.video_urls),
                "media_count": len(msg.photo_urls or []) + len(msg.video_urls or []),
                "is_reply": bool(msg.reply_to_id),
                "timestamp": msg.created_at.isoformat()
            }

            # Add caption if exists
            if msg.caption:
                notification_data["caption"] = msg.caption

            # Determine notification type
            if msg.reply_to_id:
                notification_type = "dm_reply"
                message = f"{current_user.name} replied to your message"
            elif msg.photo_urls or msg.video_urls:
                notification_type = "dm_media"
                media_type = "photo" if msg.photo_urls else "video"
                count = len(msg.photo_urls or msg.video_urls)
                message = f"{current_user.name} sent you {count} {media_type}{'s' if count > 1 else ''}"
            else:
                notification_type = "dm_message"
                message = f"{current_user.name}: {msg.text[:50]}{'...' if len(msg.text) > 50 else ''}"

            # Send WebSocket notification
            await WebSocketService.send_dm_notification(
                other_user_id,
                thread_id,
                {
                    **notification_data,
                    "message": message
                }
            )

    except Exception as e:
        # Log error but don't fail the message send
        print(f"Failed to send DM notification: {e}")

    # decorate response with defaults
    return DMMessageResponse(
        id=msg.id,
        thread_id=msg.thread_id,
        sender_id=msg.sender_id,
        text=msg.text,
        created_at=msg.created_at,
        seen=None,
        heart_count=0,
        liked_by_me=False,
        reply_to_id=msg.reply_to_id,
        reply_to_text=msg.reply_to_text,
        reply_to_sender_name=reply_sender_name,
        photo_urls=msg.photo_urls,
        video_urls=msg.video_urls,
        caption=msg.caption,
    )


@router.post("/upload/media", response_model=dict)
async def upload_dm_media(
    file: UploadFile = File(...),
    current_user: User = Depends(JWTService.get_current_user),
):
    """
    Upload media files for DM messages (photos/videos)
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/png",
                     "image/gif", "video/mp4", "video/quicktime"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file.content_type} not allowed. Allowed: {', '.join(allowed_types)}"
        )

    # Validate file size (10MB for images, 50MB for videos)
    max_size = 50 * 1024 * \
        1024 if file.content_type.startswith("video") else 10 * 1024 * 1024
    file_content = await file.read()
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {max_size // (1024*1024)}MB"
        )

    # Determine upload path
    file_ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    media_type = "videos" if file.content_type.startswith(
        "video") else "photos"
    upload_path = f"dm_media/{current_user.id}/{media_type}/{file.filename}"

    try:
        # Upload to storage
        if settings.storage_backend == "s3":
            file_url = await StorageService.upload_file_from_bytes(
                file_content,
                upload_path,
                content_type=file.content_type
            )
        else:
            # Local storage - save to media directory
            import os
            from pathlib import Path

            media_dir = Path("media") / "dm_media" / \
                str(current_user.id) / media_type
            media_dir.mkdir(parents=True, exist_ok=True)

            file_path = media_dir / file.filename
            with open(file_path, "wb") as f:
                f.write(file_content)

            file_url = f"/media/dm_media/{current_user.id}/{media_type}/{file.filename}"

        return {
            "url": file_url,
            "media_type": media_type,
            "file_size": len(file_content),
            "content_type": file.content_type
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/threads/{thread_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    thread_id: int,
    message_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a message in a DM thread (soft delete).

    Only the sender can delete their own messages.

    **Authentication Required:** Yes

    **Features:**
    - Soft delete (message is hidden but preserved)
    - Only sender can delete their messages
    - Updates thread's last activity timestamp
    - Maintains conversation history integrity

    **Rate Limiting:**
    - No specific rate limit for deletions

    **Use Cases:**
    - Remove inappropriate messages
    - Correct sent messages
    - Clean up conversation
    """
    # Verify thread exists and user is participant
    thread_result = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = thread_result.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")

    # Find and verify the message
    message_result = await db.execute(
        select(DMMessage).where(
            DMMessage.id == message_id,
            DMMessage.thread_id == thread_id,
            DMMessage.deleted_at.is_(None)
        )
    )
    message = message_result.scalars().first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Verify the current user is the sender
    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own messages"
        )

    # Soft delete the message
    message.deleted_at = func.now()
    thread.updated_at = func.now()

    await db.commit()

    # Note: We don't return anything for 204 No Content


def _participant_state_base(thread_id: int, user_id: int):
    return and_(DMParticipantState.thread_id == thread_id, DMParticipantState.user_id == user_id)


async def _get_or_create_state(db: AsyncSession, thread_id: int, user_id: int) -> DMParticipantState:
    res = await db.execute(select(DMParticipantState).where(_participant_state_base(thread_id, user_id)))
    state = res.scalars().first()
    if not state:
        state = DMParticipantState(thread_id=thread_id, user_id=user_id)
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Count unread messages across all accepted threads for this user
    base = (
        select(func.count(DMMessage.id))
        .select_from(DMMessage)
        .join(DMThread, DMMessage.thread_id == DMThread.id)
        .join(
            DMParticipantState,
            and_(DMParticipantState.thread_id == DMThread.id,
                 DMParticipantState.user_id == current_user.id),
            isouter=True,
        )
        .where(
            DMThread.status == "accepted",
            or_(DMThread.user_a_id == current_user.id,
                DMThread.user_b_id == current_user.id),
            DMMessage.sender_id != current_user.id,
            or_(DMParticipantState.last_read_at.is_(None),
                DMMessage.created_at > DMParticipantState.last_read_at),
        )
    )
    total = (await db.execute(base)).scalar_one()
    return UnreadCountResponse(unread=total)


@router.get("/threads/{thread_id}/unread-count", response_model=UnreadCountResponse)
async def thread_unread_count(
    thread_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    q = (
        select(func.count(DMMessage.id))
        .where(
            DMMessage.thread_id == thread_id,
            DMMessage.sender_id != current_user.id,
        )
        .join(
            DMParticipantState,
            and_(DMParticipantState.thread_id == DMMessage.thread_id,
                 DMParticipantState.user_id == current_user.id),
            isouter=True,
        )
        .where(or_(DMParticipantState.last_read_at.is_(None), DMMessage.created_at > DMParticipantState.last_read_at))
    )
    total = (await db.execute(q)).scalar_one()
    return UnreadCountResponse(unread=total)


@router.post("/threads/{thread_id}/mark-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    thread_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    state = await _get_or_create_state(db, thread_id, current_user.id)
    state.last_read_at = func.now()
    await db.commit()
    return None


@router.put("/threads/{thread_id}/mute", response_model=DMThreadMuteUpdate)
async def mute_thread(
    thread_id: int,
    payload: DMThreadMuteUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    state = await _get_or_create_state(db, thread_id, current_user.id)
    state.muted = payload.muted
    await db.commit()
    return DMThreadMuteUpdate(muted=state.muted)


@router.put("/threads/{thread_id}/pin", response_model=DMThreadPinUpdate)
async def pin_thread(
    thread_id: int,
    payload: DMThreadPinUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    state = await _get_or_create_state(db, thread_id, current_user.id)
    state.pinned = payload.pinned
    await db.commit()
    return DMThreadPinUpdate(pinned=state.pinned)


@router.put("/threads/{thread_id}/archive", response_model=DMThreadArchiveUpdate)
async def archive_thread(
    thread_id: int,
    payload: DMThreadArchiveUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    state = await _get_or_create_state(db, thread_id, current_user.id)
    state.archived = payload.archived
    await db.commit()
    return DMThreadArchiveUpdate(archived=state.archived)


@router.put("/threads/{thread_id}/block", response_model=DMThreadBlockUpdate)
async def block_thread(
    thread_id: int,
    payload: DMThreadBlockUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    state = await _get_or_create_state(db, thread_id, current_user.id)
    state.blocked = payload.blocked
    await db.commit()
    return DMThreadBlockUpdate(blocked=state.blocked)


@router.post("/threads/{thread_id}/typing", status_code=status.HTTP_204_NO_CONTENT)
async def set_typing(
    thread_id: int,
    payload: TypingUpdate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    state = await _get_or_create_state(db, thread_id, current_user.id)
    # set typing window ~5 seconds
    state.typing_until = (datetime.now(timezone.utc) +
                          timedelta(seconds=5)) if payload.typing else None
    await db.commit()
    return None


@router.get("/threads/{thread_id}/typing", response_model=TypingStatusResponse)
async def get_typing(
    thread_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    other_id = thread.user_a_id if current_user.id == thread.user_b_id else thread.user_b_id
    res = await db.execute(select(DMParticipantState).where(_participant_state_base(thread_id, other_id)))
    other = res.scalars().first()
    typing = False
    until = None
    if other and other.typing_until is not None and other.typing_until > datetime.now(timezone.utc):
        typing = True
        until = other.typing_until
    return TypingStatusResponse(typing=typing, until=until)


@router.get("/threads/{thread_id}/presence", response_model=PresenceResponse)
async def get_presence(
    thread_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    other_id = thread.user_a_id if current_user.id == thread.user_b_id else thread.user_b_id
    res = await db.execute(select(DMParticipantState).where(_participant_state_base(thread_id, other_id)))
    other = res.scalars().first()
    now = datetime.now(timezone.utc)
    online = False
    last_active_at = None
    if other:
        # consider typing window or last_read within 5 minutes as online
        last_active_candidates = []
        if other.typing_until:
            last_active_candidates.append(other.typing_until)
        if other.last_read_at:
            last_active_candidates.append(other.last_read_at)
        if last_active_candidates:
            last_active_at = max(last_active_candidates)
            online = (last_active_at + timedelta(minutes=5)) > now
    return PresenceResponse(user_id=other_id, online=online, last_active_at=last_active_at)


@router.post("/threads/{thread_id}/messages/{message_id}/heart", response_model=HeartResponse)
async def heart_message(
    thread_id: int,
    message_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # validate thread and message
    res = await db.execute(select(DMMessage).where(DMMessage.id == message_id))
    msg = res.scalars().first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread or msg.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    # toggle like
    existing = await db.execute(select(DMMessageLike).where(DMMessageLike.message_id == message_id, DMMessageLike.user_id == current_user.id))
    like = existing.scalars().first()
    liked = False
    if like:
        await db.delete(like)
        liked = False
    else:
        db.add(DMMessageLike(message_id=message_id, user_id=current_user.id))
        liked = True
    await db.commit()
    # count
    count = (await db.execute(select(func.count(DMMessageLike.id)).where(DMMessageLike.message_id == message_id))).scalar_one()
    return HeartResponse(liked=liked, heart_count=count)


@router.post("/threads/{thread_id}/messages/{message_id}/reactions", response_model=ReactionResponse)
async def add_message_reaction(
    thread_id: int,
    message_id: int,
    payload: ReactionCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Add an emoji reaction to a DM message.

    **Authentication Required:** Yes

    **Rate Limiting:** None (reactions are lightweight)

    **Features:**
    - Add emoji reactions to messages
    - One reaction per emoji per user per message
    - Real-time reaction updates via WebSocket
    - Automatic duplicate prevention
    """
    # Validate message exists and user has access
    msg_result = await db.execute(
        select(DMMessage).where(DMMessage.id == message_id)
    )
    msg = msg_result.scalars().first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    thread_result = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = thread_result.scalars().first()
    if not thread or msg.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Thread not found")

    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")

    # Check if reaction already exists
    existing_result = await db.execute(
        select(DMMessageReaction).where(
            DMMessageReaction.message_id == message_id,
            DMMessageReaction.user_id == current_user.id,
            DMMessageReaction.emoji == payload.emoji
        )
    )
    existing = existing_result.scalars().first()

    if existing:
        # Reaction already exists, return it
        return ReactionResponse(
            id=existing.id,
            message_id=existing.message_id,
            user_id=existing.user_id,
            emoji=existing.emoji,
            created_at=existing.created_at
        )

    # Create new reaction
    reaction = DMMessageReaction(
        message_id=message_id,
        user_id=current_user.id,
        emoji=payload.emoji
    )
    db.add(reaction)
    await db.commit()
    await db.refresh(reaction)

    # Send real-time reaction update
    try:
        await WebSocketService.send_message_reaction(
            thread_id, message_id, current_user.id, payload.emoji
        )
    except Exception as e:
        print(f"Failed to send reaction notification: {e}")

    return ReactionResponse(
        id=reaction.id,
        message_id=reaction.message_id,
        user_id=reaction.user_id,
        emoji=reaction.emoji,
        created_at=reaction.created_at
    )


@router.delete("/threads/{thread_id}/messages/{message_id}/reactions/{emoji}")
async def remove_message_reaction(
    thread_id: int,
    message_id: int,
    emoji: str,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove an emoji reaction from a DM message.

    **Authentication Required:** Yes

    **URL Parameters:**
    - `emoji`: URL-encoded emoji to remove (e.g., %F0%9F%91%8D for 👍)
    """
    # Validate message exists and user has access
    msg_result = await db.execute(
        select(DMMessage).where(DMMessage.id == message_id)
    )
    msg = msg_result.scalars().first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    thread_result = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = thread_result.scalars().first()
    if not thread or msg.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Thread not found")

    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")

    # Find and remove reaction
    reaction_result = await db.execute(
        select(DMMessageReaction).where(
            DMMessageReaction.message_id == message_id,
            DMMessageReaction.user_id == current_user.id,
            DMMessageReaction.emoji == emoji
        )
    )
    reaction = reaction_result.scalars().first()

    if not reaction:
        raise HTTPException(status_code=404, detail="Reaction not found")

    await db.delete(reaction)
    await db.commit()

    # Send real-time reaction removal update
    try:
        await WebSocketService.send_message_reaction(
            thread_id, message_id, current_user.id, f"remove:{emoji}"
        )
    except Exception as e:
        print(f"Failed to send reaction removal notification: {e}")

    return {"success": True}


@router.get("/threads/{thread_id}/messages/{message_id}/reactions")
async def get_message_reactions(
    thread_id: int,
    message_id: int,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all reactions for a DM message.

    **Authentication Required:** Yes

    **Response:**
    ```json
    {
      "👍": [
        {"user_id": 123, "user_name": "Alice"},
        {"user_id": 456, "user_name": "Bob"}
      ],
      "❤️": [
        {"user_id": 789, "user_name": "Charlie"}
      ]
    }
    ```
    """
    # Validate message exists and user has access
    msg_result = await db.execute(
        select(DMMessage).where(DMMessage.id == message_id)
    )
    msg = msg_result.scalars().first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    thread_result = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = thread_result.scalars().first()
    if not thread or msg.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Thread not found")

    if not _is_participant(thread, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")

    # Get reactions with user info
    reactions_result = await db.execute(
        select(DMMessageReaction, User.name.label("user_name")).join(
            User, DMMessageReaction.user_id == User.id
        ).where(DMMessageReaction.message_id == message_id)
    )

    # Group reactions by emoji
    reactions_by_emoji = {}
    for reaction, user_name in reactions_result:
        emoji = reaction.emoji
        if emoji not in reactions_by_emoji:
            reactions_by_emoji[emoji] = []

        reactions_by_emoji[emoji].append({
            "user_id": reaction.user_id,
            "user_name": user_name
        })

    return reactions_by_emoji
