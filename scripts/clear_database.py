#!/usr/bin/env python3
"""
Database Clear Script for Circles Application

This script clears all data from the database for testing purposes.
Use with caution as this will delete ALL data.

Usage:
    python scripts/clear_database.py
"""

from sqlalchemy import delete
from app.models import (
    User, Place, CheckIn, CheckInPhoto,
    DMThread, DMMessage, DMParticipantState, Follow, UserInterest,
    NotificationPreference, SupportTicket, Activity, CheckInComment,
    CheckInLike, OTPCode
)
from app.database import AsyncSessionLocal
import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def clear_database():
    """Clear all data from the database."""
    print("🗑️  Clearing database...")

    async with AsyncSessionLocal() as session:
        try:
            # Delete all data in reverse dependency order
            print("Deleting check-in interactions...")
            await session.execute(delete(CheckInLike))
            await session.execute(delete(CheckInComment))

            print("Deleting check-in photos...")
            await session.execute(delete(CheckInPhoto))

            # Legacy check-in collections removed

            print("Deleting check-ins...")
            await session.execute(delete(CheckIn))

            print("Deleting DM messages...")
            await session.execute(delete(DMMessage))

            print("Deleting DM participant states...")
            await session.execute(delete(DMParticipantState))

            print("Deleting DM threads...")
            await session.execute(delete(DMThread))

            print("Deleting follows...")
            await session.execute(delete(Follow))

            print("Deleting activities...")
            await session.execute(delete(Activity))

            print("Deleting support tickets...")
            await session.execute(delete(SupportTicket))

            print("Deleting notification preferences...")
            await session.execute(delete(NotificationPreference))

            print("Deleting user interests...")
            await session.execute(delete(UserInterest))

            print("Deleting OTP codes...")
            await session.execute(delete(OTPCode))

            print("Deleting places...")
            await session.execute(delete(Place))

            print("Deleting users...")
            await session.execute(delete(User))

            await session.commit()

            print("✅ Database cleared successfully!")

        except Exception as e:
            print(f"❌ Error clearing database: {e}")
            await session.rollback()
            raise


async def main():
    """Main entry point."""
    print("🚨 Circles Database Clear Script")
    print("=" * 40)
    print("⚠️  WARNING: This will delete ALL data from the database!")
    print("⚠️  This action cannot be undone!")

    # Ask for confirmation
    response = input("\nAre you sure you want to continue? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Operation cancelled.")
        return

    await clear_database()
    print("\n🎉 Database has been cleared!")
    print("You can now run the populate script to add fresh sample data.")


if __name__ == "__main__":
    asyncio.run(main())
