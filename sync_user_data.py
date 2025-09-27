#!/usr/bin/env python3
"""
Sync user data from local to AWS database to fix check-in foreign key constraints
"""

import asyncio
import sys
import os

# Add current directory to path
sys.path.append('.')

async def sync_user_data():
    """Ensure user 60 exists in AWS database to fix check-in issues"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    print("🔄 Starting user data synchronization...")

    # Direct AWS PostgreSQL database connection
    aws_database_url = "postgresql+asyncpg://circles:Circles2025SecureDB123456789@circles-db.cqdweqam0x1u.us-east-1.rds.amazonaws.com:5432/circles?ssl=require"

    print("🔗 Connecting to AWS PostgreSQL database...")
    engine = create_async_engine(aws_database_url, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            # Check if user 60 exists
            result = await db.execute(text('SELECT id, phone FROM users WHERE id = 60'))
            user = result.fetchone()

            if user:
                print(f'✅ User 60 already exists: {user}')
            else:
                print('➕ Creating user 60...')
                # Create user 60 with phone +2222222222 (simplified for PostgreSQL)
                await db.execute(text('''
                    INSERT INTO users (id, phone, is_verified, created_at, updated_at)
                    VALUES (60, '+2222222222', true, NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING
                '''))
                await db.commit()
                print('✅ User 60 created successfully')

            # Verify user exists now
            result = await db.execute(text('SELECT id, phone FROM users WHERE id = 60'))
            user = result.fetchone()
            if user:
                print(f'✅ Verified user 60 exists: {user}')
            else:
                print('❌ Failed to create user 60')

        except Exception as e:
            print(f'❌ Error syncing user data: {type(e).__name__}: {e}')
            import traceback
            traceback.print_exc()
            await db.rollback()

    await engine.dispose()
    print("🎉 User data synchronization completed!")

if __name__ == "__main__":
    asyncio.run(sync_user_data())