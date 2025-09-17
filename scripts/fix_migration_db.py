#!/usr/bin/env python3
"""
Fix the alembic migration state by updating to the latest migration.
This script should be run to fix the database state after removing a migration.
"""
import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def fix_alembic():
    # Get database URL from environment
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found")
        return
    
    # Create async engine
    engine = create_async_engine(db_url)
    
    try:
        async with engine.begin() as conn:
            # Check current alembic version
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()
            print(f"Current alembic version: {current_version}")
            
            # If it's the problematic version, update to the latest
            if current_version == "499278ad9251":
                print("Found problematic migration version, updating to latest...")
                # Update to the latest migration
                latest_version = "add_user_collections_tables"
                await conn.execute(text("UPDATE alembic_version SET version_num = :version"), 
                                 {"version": latest_version})
                print(f"Updated alembic version to: {latest_version}")
            else:
                print(f"Current version {current_version} is not the problematic one")
                
    except Exception as e:
        print(f"Error fixing migration: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_alembic())
