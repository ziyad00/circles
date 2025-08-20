from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Set, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta

from ..database import get_db
from ..services.jwt_service import JWTService
from ..models import DMThread, DMParticipantState, DMMessage


router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        # (thread_id) -> set of (user_id, websocket)
        self.active: Dict[int, Set[Tuple[int, WebSocket]]] = {}

    async def connect(self, thread_id: int, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.setdefault(thread_id, set()).add((user_id, websocket))

    def disconnect(self, thread_id: int, user_id: int, websocket: WebSocket) -> None:
        conns = self.active.get(thread_id)
        if not conns:
            return
        try:
            conns.remove((user_id, websocket))
        except KeyError:
            pass
        if not conns:
            self.active.pop(thread_id, None)

    async def broadcast(self, thread_id: int, sender_id: int, payload: dict) -> None:
        for uid, ws in list(self.active.get(thread_id, set())):
            if uid == sender_id:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                # Ignore send errors
                pass


manager = ConnectionManager()


async def _authenticate(websocket: WebSocket) -> int | None:
    token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        payload = JWTService.decode_token(token)
        user_id = int(payload.get("sub"))
        return user_id
    except Exception:
        return None


@router.websocket("/ws/dms/{thread_id}")
async def dm_ws(websocket: WebSocket, thread_id: int, db: AsyncSession = Depends(get_db)):
    user_id = await _authenticate(websocket)
    if not user_id:
        await websocket.close(code=4401)
        return
    # authorize participant and accepted status
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalars().first()
    if not thread or user_id not in (thread.user_a_id, thread.user_b_id) or thread.status != "accepted":
        await websocket.close(code=4403)
        return

    await manager.connect(thread_id, user_id, websocket)
    try:
        # announce presence online
        await manager.broadcast(thread_id, user_id, {"type": "presence", "user_id": user_id, "online": True})
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "typing":
                typing = bool(data.get("typing", False))
                # update typing_until ~5s
                state = await _get_or_create_state(db, thread_id, user_id)
                state.typing_until = (datetime.now(timezone.utc) + timedelta(seconds=5)) if typing else None
                await db.commit()
                await manager.broadcast(thread_id, user_id, {"type": "typing", "user_id": user_id, "typing": typing})
            elif msg_type == "message":
                text = (data.get("text") or "").strip()
                if not text:
                    await websocket.send_json({"type": "error", "detail": "Empty message"})
                    continue
                # prevent sending if the other participant blocked me
                other_id = thread.user_a_id if user_id == thread.user_b_id else thread.user_b_id
                other_state = await _get_or_create_state(db, thread_id, other_id)
                if other_state and getattr(other_state, "blocked", False):
                    await websocket.send_json({"type": "error", "detail": "You are blocked by this user"})
                    continue
                msg = DMMessage(thread_id=thread_id, sender_id=user_id, text=text)
                db.add(msg)
                # bump thread updated_at
                thread.updated_at = datetime.now(timezone.utc)
                await db.commit()
                await db.refresh(msg)
                payload = {
                    "type": "message",
                    "message": {
                        "id": msg.id,
                        "thread_id": msg.thread_id,
                        "sender_id": msg.sender_id,
                        "text": msg.text,
                        "created_at": msg.created_at.isoformat(),
                    },
                }
                # echo to sender and broadcast to other
                try:
                    await websocket.send_json(payload)
                except Exception:
                    pass
                await manager.broadcast(thread_id, user_id, payload)
            elif msg_type == "mark_read":
                state = await _get_or_create_state(db, thread_id, user_id)
                state.last_read_at = datetime.now(timezone.utc)
                await db.commit()
                await manager.broadcast(thread_id, user_id, {"type": "read", "user_id": user_id, "last_read_at": state.last_read_at.isoformat()})
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                # ignore unknown
                pass
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(thread_id, user_id, websocket)
        await manager.broadcast(thread_id, user_id, {"type": "presence", "user_id": user_id, "online": False})


async def _get_or_create_state(db: AsyncSession, thread_id: int, user_id: int) -> DMParticipantState:
    res = await db.execute(select(DMParticipantState).where(DMParticipantState.thread_id == thread_id, DMParticipantState.user_id == user_id))
    state = res.scalars().first()
    if not state:
        state = DMParticipantState(thread_id=thread_id, user_id=user_id)
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state


