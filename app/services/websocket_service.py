from typing import Dict, Any, Optional
from datetime import datetime, timezone
import asyncio
from fastapi import WebSocket

from ..routers.dms_ws import manager


class WebSocketService:
    """Service for sending real-time notifications and updates via WebSocket"""
    
    @staticmethod
    async def send_notification(user_id: int, notification_type: str, data: Dict[str, Any]) -> None:
        """Send a notification to a specific user"""
        payload = {
            "type": "notification",
            "notification_type": notification_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await manager.send_to_user(user_id, payload)
    
    @staticmethod
    async def send_dm_notification(user_id: int, thread_id: int, message_data: Dict[str, Any]) -> None:
        """Send DM notification to user"""
        payload = {
            "type": "dm_notification",
            "thread_id": thread_id,
            "message": message_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await manager.send_to_user(user_id, payload)
    
    @staticmethod
    async def send_follow_notification(user_id: int, follower_data: Dict[str, Any]) -> None:
        """Send follow notification"""
        await WebSocketService.send_notification(
            user_id, 
            "new_follower", 
            {
                "follower": follower_data,
                "message": f"{follower_data.get('name', 'Someone')} started following you"
            }
        )
    
    @staticmethod
    async def send_checkin_notification(user_id: int, checkin_data: Dict[str, Any]) -> None:
        """Send check-in notification to followers"""
        await WebSocketService.send_notification(
            user_id,
            "new_checkin",
            {
                "checkin": checkin_data,
                "message": f"{checkin_data.get('user_name', 'Someone')} checked in at {checkin_data.get('place_name', 'a place')}"
            }
        )
    
    @staticmethod
    async def send_like_notification(user_id: int, like_data: Dict[str, Any]) -> None:
        """Send like notification"""
        await WebSocketService.send_notification(
            user_id,
            "new_like",
            {
                "like": like_data,
                "message": f"{like_data.get('user_name', 'Someone')} liked your check-in"
            }
        )
    
    @staticmethod
    async def send_comment_notification(user_id: int, comment_data: Dict[str, Any]) -> None:
        """Send comment notification"""
        await WebSocketService.send_notification(
            user_id,
            "new_comment",
            {
                "comment": comment_data,
                "message": f"{comment_data.get('user_name', 'Someone')} commented on your check-in"
            }
        )
    
    @staticmethod
    async def send_dm_request_notification(user_id: int, request_data: Dict[str, Any]) -> None:
        """Send DM request notification"""
        await WebSocketService.send_notification(
            user_id,
            "dm_request",
            {
                "request": request_data,
                "message": f"{request_data.get('user_name', 'Someone')} sent you a DM request"
            }
        )
    
    @staticmethod
    async def send_system_notification(user_id: int, title: str, message: str, notification_type: str = "info") -> None:
        """Send system notification"""
        await WebSocketService.send_notification(
            user_id,
            "system",
            {
                "title": title,
                "message": message,
                "notification_type": notification_type
            }
        )
    
    @staticmethod
    async def broadcast_to_thread(thread_id: int, sender_id: int, message_type: str, data: Dict[str, Any]) -> None:
        """Broadcast message to all participants in a thread"""
        payload = {
            "type": message_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await manager.broadcast(thread_id, sender_id, payload)
    
    @staticmethod
    async def send_presence_update(thread_id: int, user_id: int, online: bool, user_info: Optional[Dict[str, Any]] = None) -> None:
        """Send presence update to thread participants"""
        await manager.broadcast_presence(thread_id, user_id, online)
    
    @staticmethod
    async def send_typing_indicator(thread_id: int, user_id: int, typing: bool) -> None:
        """Send typing indicator to thread participants"""
        await manager.broadcast_typing(thread_id, user_id, typing)
    
    @staticmethod
    async def send_read_receipt(thread_id: int, user_id: int, last_read_at: datetime) -> None:
        """Send read receipt to thread participants"""
        await manager.broadcast_read_receipt(thread_id, user_id, last_read_at)
    
    @staticmethod
    async def send_message_reaction(thread_id: int, message_id: int, user_id: int, reaction: str) -> None:
        """Send message reaction to thread participants"""
        await manager.broadcast_reaction(thread_id, message_id, user_id, reaction)
    
    @staticmethod
    def is_user_online(user_id: int) -> bool:
        """Check if a user is currently online"""
        return user_id in manager.user_connections
    
    @staticmethod
    def get_user_connections(user_id: int) -> int:
        """Get number of active connections for a user"""
        user_conns = manager.user_connections.get(user_id, set())
        return len(user_conns)
    
    @staticmethod
    def get_thread_participants(thread_id: int) -> list:
        """Get list of online participants in a thread"""
        thread_conns = manager.active.get(thread_id, set())
        return [uid for uid, _, _ in thread_conns]
    
    @staticmethod
    async def send_bulk_notification(user_ids: list[int], notification_type: str, data: Dict[str, Any]) -> None:
        """Send notification to multiple users"""
        tasks = []
        for user_id in user_ids:
            task = WebSocketService.send_notification(user_id, notification_type, data)
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    @staticmethod
    async def send_activity_update(user_id: int, activity_type: str, activity_data: Dict[str, Any]) -> None:
        """Send activity update (for activity feed)"""
        await WebSocketService.send_notification(
            user_id,
            "activity_update",
            {
                "activity_type": activity_type,
                "activity": activity_data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
    
    @staticmethod
    async def send_place_update(place_id: int, update_type: str, update_data: Dict[str, Any]) -> None:
        """Send place-related updates (new check-ins, reviews, etc.)"""
        # This would need to be implemented based on who should receive place updates
        # For now, we'll just log it
        print(f"Place update for place {place_id}: {update_type} - {update_data}")
    
    @staticmethod
    async def send_collection_update(user_id: int, collection_data: Dict[str, Any]) -> None:
        """Send collection update notification"""
        await WebSocketService.send_notification(
            user_id,
            "collection_update",
            {
                "collection": collection_data,
                "message": f"Your collection '{collection_data.get('name', 'Collection')}' was updated"
            }
        )
    
    @staticmethod
    async def send_support_notification(user_id: int, ticket_data: Dict[str, Any]) -> None:
        """Send support ticket notification"""
        await WebSocketService.send_notification(
            user_id,
            "support_update",
            {
                "ticket": ticket_data,
                "message": f"Your support ticket '{ticket_data.get('subject', 'Ticket')}' was updated"
            }
        )
