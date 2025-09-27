#!/usr/bin/env python3
"""
ECS task to sync user data - create user 60 in AWS database
"""

import asyncio
import sys
sys.path.append('.')

async def create_user():
    from app.database import get_db
    from sqlalchemy import text

    print("Starting user sync in ECS task...")

    async for db in get_db():
        try:
            # Check if user 60 exists
            result = await db.execute(text('SELECT id, phone FROM users WHERE id = 60'))
            user = result.fetchone()

            if user:
                print(f'✅ User 60 already exists: {user}')
            else:
                print('➕ Creating user 60...')
                await db.execute(text('''
                    INSERT INTO users (id, phone, is_verified, created_at, updated_at)
                    VALUES (60, '+2222222222', true, NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING
                '''))
                await db.commit()

                # Verify creation
                result = await db.execute(text('SELECT id, phone FROM users WHERE id = 60'))
                user = result.fetchone()

                if user:
                    print(f'✅ User 60 created successfully: {user}')
                else:
                    print('❌ Failed to create user 60')

        except Exception as e:
            print(f'❌ Error: {e}')
        break

if __name__ == "__main__":
    asyncio.run(create_user())