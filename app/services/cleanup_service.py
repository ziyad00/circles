"""
Cleanup service for handling disappearing messages and other cleanup tasks.
"""
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session_maker
from ..models import DMMessage

logger = logging.getLogger(__name__)


class CleanupService:
    @staticmethod
    async def cleanup_expired_messages():
        """Delete messages that have expired (disappearing messages)."""
        try:
            async with async_session_maker() as db:
                # Find messages that have expired
                now = datetime.now(timezone.utc)
                expired_messages = await db.execute(
                    select(DMMessage).where(
                        and_(
                            DMMessage.expires_at.is_not(None),
                            DMMessage.expires_at <= now,
                            DMMessage.deleted_at.is_(None)  # Not already deleted
                        )
                    )
                )

                expired_count = 0
                for message in expired_messages.scalars().all():
                    # Soft delete the expired message
                    message.deleted_at = now
                    message.deleted_by_user_id = None  # System deleted
                    expired_count += 1

                if expired_count > 0:
                    await db.commit()
                    logger.info(f"Cleaned up {expired_count} expired messages")

        except Exception as e:
            logger.error(f"Error cleaning up expired messages: {e}")

    @staticmethod
    async def start_cleanup_scheduler():
        """Start the background cleanup scheduler."""
        logger.info("Starting cleanup scheduler...")

        while True:
            try:
                await CleanupService.cleanup_expired_messages()
                # Run cleanup every 5 minutes
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Error in cleanup scheduler: {e}")
                # Wait a bit before retrying
                await asyncio.sleep(60)