#!/bin/bash
set -e

echo "Starting application..."

# Fix the alembic migration issue if it exists
echo "Checking and fixing alembic migration state..."
python -c "
import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def fix_alembic():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print('DATABASE_URL not found')
        return
    
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text('SELECT version_num FROM alembic_version'))
            current_version = result.scalar()
            print(f'Current alembic version: {current_version}')
            
            # Check if there are multiple versions in the alembic_version table
            result = await conn.execute(text('SELECT COUNT(*) FROM alembic_version'))
            version_count = result.scalar()
            print(f'Number of versions in alembic_version table: {version_count}')
            
            if version_count > 1:
                print('Found multiple versions, cleaning up...')
                # Delete all versions and insert the correct one
                await conn.execute(text('DELETE FROM alembic_version'))
                await conn.execute(text('INSERT INTO alembic_version (version_num) VALUES (:version)'),
                                 {'version': '499278ad9251'})
                print('Cleaned up alembic_version table and set to: 499278ad9251')
            elif current_version == 'add_user_collections_tables':
                print('Found conflicting migration version add_user_collections_tables')
                # Check if the migration tables actually exist
                result = await conn.execute(text('''
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = 'user_collections'
                    );
                '''))
                tables_exist = result.scalar()
                print(f'User collections tables exist: {tables_exist}')

                if tables_exist:
                    # Tables exist, so the migration was already applied, update to correct version
                    print('Tables exist, updating to correct migration version')
                    await conn.execute(text('UPDATE alembic_version SET version_num = :version'),
                                     {'version': '499278ad9251'})
                    print('Updated alembic version to: 499278ad9251 (correct version)')
                else:
                    # Tables don't exist, rollback to previous version and let alembic rerun
                    print('Tables missing, rolling back to previous version')
                    await conn.execute(text('UPDATE alembic_version SET version_num = :version'),
                                     {'version': 'fdeec55cbdb7'})
                    print('Rollback: Updated alembic version to: fdeec55cbdb7')
            elif current_version == '499278ad9251':
                print('Found migration version 499278ad9251')
                # Check if the migration tables actually exist
                result = await conn.execute(text('''
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = 'user_collections'
                    );
                '''))
                tables_exist = result.scalar()
                print(f'User collections tables exist: {tables_exist}')

                # Check if availability_status column exists in users table
                result = await conn.execute(text('''
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_schema = 'public'
                        AND table_name = 'users'
                        AND column_name = 'availability_status'
                    );
                '''))
                availability_column_exists = result.scalar()
                print(f'Availability status column exists: {availability_column_exists}')

                if tables_exist and availability_column_exists:
                    # Both tables and column exist, update to the latest version
                    print('Both tables and column exist, updating to latest version')
                    await conn.execute(text('UPDATE alembic_version SET version_num = :version'),
                                     {'version': 'comprehensive_privacy_controls'})
                    print('Updated alembic version to: comprehensive_privacy_controls')
                elif tables_exist:
                    # Tables exist but column doesn't, update to version before the column addition
                    print('Tables exist but column missing, updating to version before column addition')
                    await conn.execute(text('UPDATE alembic_version SET version_num = :version'),
                                     {'version': 'fdeec55cbdb7'})
                    print('Updated alembic version to: fdeec55cbdb7')
                else:
                    # Tables don't exist, rollback to previous version and let alembic rerun
                    print('Tables missing, rolling back to previous version')
                    await conn.execute(text('UPDATE alembic_version SET version_num = :version'),
                                     {'version': 'fdeec55cbdb7'})
                    print('Rollback: Updated alembic version to: fdeec55cbdb7')
            else:
                print(f'Current version {current_version} is not the problematic one')
    except Exception as e:
        print(f'Error fixing migration: {e}')
    finally:
        await engine.dispose()

asyncio.run(fix_alembic())
"

# Run alembic migrations to ensure database is up to date
echo "Running alembic migrations..."
# Check for multiple heads and resolve them
alembic heads
echo "Attempting to upgrade to heads (all heads)..."

# First, try to fix the alembic_version column size if it's too small
python -c "
import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def fix_alembic_column():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print('DATABASE_URL not found')
        return
    
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            # Check current column size
            result = await conn.execute(text('''
                SELECT character_maximum_length 
                FROM information_schema.columns 
                WHERE table_name = 'alembic_version' 
                AND column_name = 'version_num'
            '''))
            current_size = result.scalar()
            print(f'Current alembic_version column size: {current_size}')
            
            if current_size and current_size < 50:
                print('Expanding alembic_version column to accommodate longer version strings...')
                await conn.execute(text('ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(100)'))
                print('Column size updated to 100 characters')
            else:
                print('Column size is already sufficient')
    except Exception as e:
        print(f'Error fixing column size: {e}')
    finally:
        await engine.dispose()

asyncio.run(fix_alembic_column())
"

# Now try the migration
alembic upgrade heads

# Start the application
echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
