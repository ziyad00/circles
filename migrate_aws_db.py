#!/usr/bin/env python3
"""
Migrate AWS PostgreSQL database to match current schema
"""

import asyncio
import sys
import os
sys.path.append('.')

async def migrate_database():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    print("🔄 Starting AWS database migration...")

    # AWS database connection
    DATABASE_URL = "postgresql+asyncpg://circles:Circles2025SecureDB123456789@circles-db.cqdweqam0x1u.us-east-1.rds.amazonaws.com:5432/circles?ssl=require"

    engine = create_async_engine(DATABASE_URL, echo=True)

    async with engine.begin() as conn:
        try:
            # Get current columns
            result = await conn.execute(text('''
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'places' AND table_schema = 'public'
            '''))
            existing_columns = {row.column_name for row in result}
            print(f"📋 Existing columns: {sorted(existing_columns)}")

            # Define required columns that are missing
            required_columns = {
                'cross_street': 'VARCHAR',
                'formatted_address': 'TEXT',
                'distance_meters': 'FLOAT',
                'venue_created_at': 'TIMESTAMP WITH TIME ZONE',
                'photo_url': 'VARCHAR',
                'additional_photos': 'TEXT'
            }

            # Add missing columns
            for column_name, column_type in required_columns.items():
                if column_name not in existing_columns:
                    print(f"➕ Adding column: {column_name} ({column_type})")
                    await conn.execute(text(f'''
                        ALTER TABLE places
                        ADD COLUMN {column_name} {column_type}
                    '''))
                else:
                    print(f"✅ Column {column_name} already exists")

            print("💾 Migration completed successfully!")

        except Exception as e:
            print(f"❌ Migration error: {e}")
            raise

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate_database())