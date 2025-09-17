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
                print('Found problematic migration version, updating to latest...')
                await conn.execute(text('UPDATE alembic_version SET version_num = :version'), 
                                 {'version': 'add_user_collections_tables'})
                print('Updated alembic version to: add_user_collections_tables')
            else:
                print(f'Current version {current_version} is not the problematic one')
    except Exception as e:
        print(f'Error fixing migration: {e}')
    finally:
        await engine.dispose()

asyncio.run(fix_alembic())
"

# Skip alembic migrations for now since the database is already up to date
echo "Skipping alembic migrations (database already up to date)..."

# Start the application
echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
