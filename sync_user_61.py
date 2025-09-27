#!/usr/bin/env python3
"""
ECS task to sync user data - create user 61 in AWS database for current session
"""

import asyncio
import sys
sys.path.append('.')

async def create_user():
    from app.database import get_db
    from sqlalchemy import text
    import os

    print("Starting user 61 sync in ECS task...")

    # Set AWS database URL environment variable
    os.environ["APP_DATABASE_URL"] = "postgresql+asyncpg://circles:Circles2025SecureDB123456789@circles-db.cqdweqam0x1u.us-east-1.rds.amazonaws.com:5432/circles?ssl=require"

    async for db in get_db():
        try:
            # Check if user 61 exists
            result = await db.execute(text('SELECT id, phone FROM users WHERE id = 61'))
            user = result.fetchone()

            if user:
                print(f'✅ User 61 already exists: {user}')
            else:
                print('➕ Creating user 61...')
                await db.execute(text('''
                    INSERT INTO users (id, phone, is_verified, created_at, updated_at)
                    VALUES (61, '+60123456789', true, NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING
                '''))
                await db.commit()

                # Verify creation
                result = await db.execute(text('SELECT id, phone FROM users WHERE id = 61'))
                user = result.fetchone()

                if user:
                    print(f'✅ User 61 created successfully: {user}')
                else:
                    print('❌ Failed to create user 61')

        except Exception as e:
            print(f'❌ Error: {e}')
        break

if __name__ == "__main__":
    asyncio.run(create_user())