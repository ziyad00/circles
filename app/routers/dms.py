from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, desc
from typing import Optional

from ..database import get_db
from ..models import User, DMThread, DMMessage, DMParticipantState, DMMessageLike, Follow
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
)
from ..services.jwt_service import JWTService


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
DM_REQUEST_LIMIT = 5  # requests per minute
DM_MESSAGE_LIMIT = 20  # messages per minute


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

    if payload.recipient_email == current_user.email:
        raise HTTPException(status_code=400, detail="Cannot message yourself")
    # find recipient
    res = await db.execute(select(User).where(User.email == payload.recipient_email))
    recipient = res.scalars().first()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    # enforce recipient dm_privacy strictly
    # everyone | followers | no_one
    if recipient.dm_privacy == "no_one":
        raise HTTPException(
            status_code=403, detail="Recipient does not accept DMs")
    if recipient.dm_privacy == "followers":
        resf = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == recipient.id))
        if resf.scalars().first() is None:
            raise HTTPException(
                status_code=403, detail="Recipient accepts DMs from followers only")

    a, b = _normalize_pair(current_user.id, recipient.id)
    # if sender follows recipient and recipient allows followers DMs, auto-accept; else pending
    res_follow = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.followee_id == recipient.id))
    follows = res_follow.scalars().first()
    # existing thread
    res = await db.execute(select(DMThread).where(DMThread.user_a_id == a, DMThread.user_b_id == b))
    thread = res.scalars().first()
    if not thread:
        auto = bool(follows) and recipient.dm_privacy in (
            "everyone", "followers")
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
    # Join participant state for current user to filter by pinned/archived and enable search ordering
    base = (
        select(DMThread)
        .join(
            DMParticipantState,
            and_(
                DMParticipantState.thread_id == DMThread.id,
                DMParticipantState.user_id == current_user.id,
            ),
            isouter=True,
        )
        .where(
            DMThread.status == "accepted",
            or_(DMThread.user_a_id == current_user.id,
                DMThread.user_b_id == current_user.id),
            # archived filter
            or_(include_archived, DMParticipantState.archived.is_(
                False) | DMParticipantState.archived.is_(None)),
            # pinned filter (optional)
            or_(~only_pinned, DMParticipantState.pinned.is_(True)),
        )
    )
    if q:
        # search by other participant name/email via subquery on last message text as well
        # filter where last message text ilike q OR other user's email/name ilike q
        # last message subquery
        last_msg_subq = (
            select(DMMessage.thread_id, func.max(
                DMMessage.created_at).label("last_ts"))
            .group_by(DMMessage.thread_id)
            .subquery()
        )
        base = (
            base.join(last_msg_subq, last_msg_subq.c.thread_id ==
                      DMThread.id, isouter=True)
            .join(DMMessage, and_(DMMessage.thread_id == DMThread.id, DMMessage.created_at == last_msg_subq.c.last_ts), isouter=True)
        )
        # other participant lookup
        other_id = func.case(
            (DMThread.user_a_id == current_user.id, DMThread.user_b_id),
            else_=DMThread.user_a_id,
        )
        other_user_subq = select(User.id, User.email, User.name).subquery()
        base = base.join(other_user_subq, other_user_subq.c.id ==
                         other_id, isouter=True)
        like = f"%{q}%"
        base = base.where(
            or_(
                DMMessage.text.ilike(like),
                other_user_subq.c.email.ilike(like),
                other_user_subq.c.name.ilike(like),
            )
        )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    # order: pinned first, then updated_at desc
    stmt = base.order_by(desc(DMParticipantState.pinned.nullslast()), desc(
        DMThread.updated_at)).offset(offset).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
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
    base = select(DMMessage).where(DMMessage.thread_id == thread_id)
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
    msg = DMMessage(thread_id=thread_id,
                    sender_id=current_user.id, text=payload.text)
    db.add(msg)
    # bump thread updated_at
    thread.updated_at = func.now()
    await db.commit()
    await db.refresh(msg)
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
    )


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
