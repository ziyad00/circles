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
            
            if current_version == '499278ad9251':
                print('Found problematic migration version 499278ad9251')
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
                    # Tables exist, so the migration was already applied, update to latest known good version
                    print('Tables exist but version is problematic, updating to latest migration')
                    await conn.execute(text('UPDATE alembic_version SET version_num = :version'),
                                     {'version': 'fdeec55cbdb7'})
                    print('Updated alembic version to: fdeec55cbdb7 (latest known good)')
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
alembic upgrade head

# Start the application
echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
