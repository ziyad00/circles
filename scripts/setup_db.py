#!/usr/bin/env python3
"""
Database setup script for Circles application.
This script helps initialize the PostgreSQL database and run migrations.
"""

from app.database import create_tables, engine
from app.config import settings
import asyncio
import sys
import os

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)


async def setup_database():
    """Setup database tables"""
    print("Setting up database...")
    print(f"Database URL: {settings.database_url}")

    try:
        # Test database connection
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: sync_conn.execute("SELECT 1"))
        print("✅ Database connection successful")

        # Create tables
        await create_tables()
        print("✅ Database tables created successfully")

    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        print("\nMake sure PostgreSQL is running:")
        print("  docker-compose up -d postgres")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(setup_database())
