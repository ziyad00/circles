from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Set, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone, timedelta
import asyncio
import json

from ..database import get_db
from ..services.jwt_service import JWTService
from ..models import DMThread, DMParticipantState, DMMessage, User


router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        # (thread_id) -> dict of {user_id: (websocket, last_ping)}
        self.active: Dict[int, Dict[int, Tuple[WebSocket, datetime]]] = {}
        # (user_id) -> set of (thread_id, websocket)
        self.user_connections: Dict[int, Set[Tuple[int, WebSocket]]] = {}
        # Background task for cleanup
        self.cleanup_task: Optional[asyncio.Task] = None
        # Flag to stop cleanup task
        self._shutdown = False

    async def connect(self, thread_id: int, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        now = datetime.now(timezone.utc)

        # Add to thread connections
        if thread_id not in self.active:
            self.active[thread_id] = {}
        self.active[thread_id][user_id] = (websocket, now)

        # Add to user connections
        self.user_connections.setdefault(
            user_id, set()).add((thread_id, websocket))

        # Start cleanup task if not running
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(
                self._cleanup_stale_connections())

    def disconnect(self, thread_id: int, user_id: int, websocket: WebSocket) -> None:
        # Remove from thread connections
        if thread_id in self.active and user_id in self.active[thread_id]:
            del self.active[thread_id][user_id]
            if not self.active[thread_id]:
                del self.active[thread_id]

        # Remove from user connections
        user_conns = self.user_connections.get(user_id)
        if user_conns:
            user_conns.discard((thread_id, websocket))
            if not user_conns:
                self.user_connections.pop(user_id, None)

    async def broadcast(self, thread_id: int, sender_id: int, payload: dict) -> None:
        """Broadcast message to all participants in a thread except sender"""
        thread_connections = self.active.get(thread_id, {})
        for uid, (ws, _) in list(thread_connections.items()):
            if uid == sender_id:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                # Remove stale connection
                self.disconnect(thread_id, uid, ws)

    async def send_to_user(self, user_id: int, payload: dict) -> None:
        """Send message to all connections of a specific user"""
        user_conns = self.user_connections.get(user_id, set())
        for thread_id, ws in list(user_conns):
            try:
                await ws.send_json(payload)
            except Exception:
                # Remove stale connection
                self.disconnect(thread_id, user_id, ws)

    async def broadcast_presence(self, thread_id: int, user_id: int, online: bool) -> None:
        """Broadcast presence update to thread participants"""
        payload = {
            "type": "presence",
            "user_id": user_id,
            "online": online,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast(thread_id, user_id, payload)

    async def broadcast_typing(self, thread_id: int, user_id: int, typing: bool) -> None:
        """Broadcast typing indicator"""
        payload = {
            "type": "typing",
            "user_id": user_id,
            "typing": typing,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast(thread_id, user_id, payload)

    async def broadcast_message(self, thread_id: int, message_data: dict) -> None:
        """Broadcast new message to thread participants"""
        payload = {
            "type": "message",
            "message": message_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        # Send to all participants including sender (for echo)
        thread_connections = self.active.get(thread_id, {})
        for uid, (ws, _) in list(thread_connections.items()):
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(thread_id, uid, ws)

    async def broadcast_reaction(self, thread_id: int, message_id: int, user_id: int, reaction: str) -> None:
        """Broadcast message reaction"""
        payload = {
            "type": "reaction",
            "message_id": message_id,
            "user_id": user_id,
            "reaction": reaction,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast(thread_id, user_id, payload)

    async def broadcast_read_receipt(self, thread_id: int, user_id: int, last_read_at: datetime) -> None:
        """Broadcast read receipt"""
        payload = {
            "type": "read_receipt",
            "user_id": user_id,
            "last_read_at": last_read_at.isoformat(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast(thread_id, user_id, payload)

    async def _cleanup_stale_connections(self) -> None:
        """Background task to clean up stale connections"""
        while not self._shutdown:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                now = datetime.now(timezone.utc)
                stale_connections = []

                for thread_id, connections in self.active.items():
                    for user_id, (ws, last_ping) in connections.items():
                        # Consider connection stale if no ping for 2 minutes
                        if (now - last_ping) > timedelta(minutes=2):
                            stale_connections.append((thread_id, user_id, ws))

                for thread_id, user_id, ws in stale_connections:
                    self.disconnect(thread_id, user_id, ws)
                    try:
                        await ws.close(code=1000)
                    except Exception:
                        pass

            except Exception:
                # Continue cleanup even if there are errors
                pass

        logger.info("WebSocket cleanup task stopped")

    async def shutdown(self) -> None:
        """Shutdown the connection manager and stop cleanup task"""
        self._shutdown = True
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Connection manager shutdown complete")

    def update_ping(self, thread_id: int, user_id: int, websocket: WebSocket) -> None:
        """Update last ping time for a connection"""
        if thread_id in self.active and user_id in self.active[thread_id]:
            # Update the timestamp for the existing connection
            self.active[thread_id][user_id] = (
                websocket, datetime.now(timezone.utc))


manager = ConnectionManager()


async def _authenticate(websocket: WebSocket) -> int | None:
    token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        payload = JWTService.verify_token(token)
        user_id = int(payload.get("sub"))
        return user_id
    except Exception:
        return None


async def _get_user_info(db: AsyncSession, user_id: int) -> dict:
    """Get user information for presence updates"""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if user:
        return {
            "id": user.id,
            "name": user.name or user.email,
            "avatar_url": user.avatar_url
        }
    return {"id": user_id, "name": "Unknown", "avatar_url": None}


async def _get_or_create_state(db: AsyncSession, thread_id: int, user_id: int) -> DMParticipantState:
    res = await db.execute(select(DMParticipantState).where(
        DMParticipantState.thread_id == thread_id,
        DMParticipantState.user_id == user_id
    ))
    state = res.scalar_one_or_none()
    if not state:
        state = DMParticipantState(thread_id=thread_id, user_id=user_id)
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state


@router.websocket("/ws/dms/{thread_id}")
async def dm_ws(websocket: WebSocket, thread_id: int, db: AsyncSession = Depends(get_db)):
    user_id = await _authenticate(websocket)
    if not user_id:
        await websocket.close(code=4401)
        return

    # Authorize participant and accepted status
    res = await db.execute(select(DMThread).where(DMThread.id == thread_id))
    thread = res.scalar_one_or_none()
    if not thread or user_id not in (thread.user_a_id, thread.user_b_id) or thread.status != "accepted":
        await websocket.close(code=4403)
        return

    await manager.connect(thread_id, user_id, websocket)

    try:
        # Get user info for presence
        user_info = await _get_user_info(db, user_id)

        # Announce presence online
        await manager.broadcast_presence(thread_id, user_id, True)

        # Send connection confirmation
        await websocket.send_json({
            "type": "connection_established",
            "thread_id": thread_id,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Send current thread participants info
        other_user_id = thread.user_a_id if user_id == thread.user_b_id else thread.user_b_id
        other_user_info = await _get_user_info(db, other_user_id)

        # Check if other user is online
        thread_connections = manager.active.get(thread_id, {})
        other_online = other_user_id in thread_connections

        await websocket.send_json({
            "type": "thread_info",
            "participants": [user_info, other_user_info],
            "other_user_online": other_online,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                manager.update_ping(thread_id, user_id, websocket)
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            elif msg_type == "typing":
                typing = bool(data.get("typing", False))
                # Update typing_until ~5s
                state = await _get_or_create_state(db, thread_id, user_id)
                state.typing_until = (datetime.now(
                    timezone.utc) + timedelta(seconds=5)) if typing else None
                await db.commit()
                await manager.broadcast_typing(thread_id, user_id, typing)

            elif msg_type == "message":
                text = (data.get("text") or "").strip()
                if not text:
                    await websocket.send_json({
                        "type": "error",
                        "detail": "Empty message",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    continue

                # Prevent sending if the other participant blocked me
                other_id = thread.user_a_id if user_id == thread.user_b_id else thread.user_b_id
                other_state = await _get_or_create_state(db, thread_id, other_id)
                if other_state and getattr(other_state, "blocked", False):
                    await websocket.send_json({
                        "type": "error",
                        "detail": "You are blocked by this user",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    continue

                # Create message
                msg = DMMessage(thread_id=thread_id,
                                sender_id=user_id, text=text)
                db.add(msg)

                # Bump thread updated_at
                thread.updated_at = datetime.now(timezone.utc)
                await db.commit()
                await db.refresh(msg)

                # Prepare message data
                message_data = {
                    "id": msg.id,
                    "thread_id": msg.thread_id,
                    "sender_id": msg.sender_id,
                    "text": msg.text,
                    "created_at": msg.created_at.isoformat(),
                    "sender_info": user_info
                }

                # Broadcast message
                await manager.broadcast_message(thread_id, message_data)

            elif msg_type == "mark_read":
                state = await _get_or_create_state(db, thread_id, user_id)
                state.last_read_at = datetime.now(timezone.utc)
                await db.commit()
                await manager.broadcast_read_receipt(thread_id, user_id, state.last_read_at)

            elif msg_type == "reaction":
                message_id = data.get("message_id")
                reaction = data.get("reaction", "❤️")

                if not message_id:
                    await websocket.send_json({
                        "type": "error",
                        "detail": "Message ID required",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    continue

                # Here you would add the reaction to the database
                # For now, just broadcast the reaction
                await manager.broadcast_reaction(thread_id, message_id, user_id, reaction)

            elif msg_type == "typing_stop":
                # Stop typing indicator
                state = await _get_or_create_state(db, thread_id, user_id)
                state.typing_until = None
                await db.commit()
                await manager.broadcast_typing(thread_id, user_id, False)

            else:
                # Ignore unknown message types
                await websocket.send_json({
                    "type": "error",
                    "detail": f"Unknown message type: {msg_type}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        # Log error and close connection
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(thread_id, user_id, websocket)
        await manager.broadcast_presence(thread_id, user_id, False)


@router.websocket("/ws/user/{user_id}")
async def user_ws(websocket: WebSocket, user_id: int, db: AsyncSession = Depends(get_db)):
    """WebSocket connection for user-wide notifications and updates"""
    authenticated_user_id = await _authenticate(websocket)
    if not authenticated_user_id or authenticated_user_id != user_id:
        await websocket.close(code=4401)
        return

    # Use thread_id 0 for user-wide connections
    await manager.connect(0, user_id, websocket)

    try:
        await websocket.send_json({
            "type": "connection_established",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                manager.update_ping(0, user_id, websocket)
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            else:
                # Handle user-specific messages here
                pass

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(0, user_id, websocket)
