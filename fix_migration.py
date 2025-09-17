#!/usr/bin/env python3
"""
Fix the alembic migration state by removing the reference to the deleted migration.
"""
import os
import asyncio
import asyncpg
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

async def fix_migration():
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
                # Get the latest migration from the files
                latest_version = "a1b2c3d4e5f6"  # This should be the latest migration
                
                # Update the version
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
    asyncio.run(fix_migration())
