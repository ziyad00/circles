#!/usr/bin/env python3
"""
Database migration script to add missing columns to the places table.
This script can be run from within the ECS container.
"""

import asyncio
import asyncpg
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

async def add_missing_columns_async():
    """Add missing columns using asyncpg"""
    # Get database URL from environment
    db_url = os.getenv('APP_DATABASE_URL')
    if not db_url:
        print("APP_DATABASE_URL not found")
        return False
    
    # Convert SQLAlchemy URL to asyncpg format
    if 'postgresql+asyncpg://' in db_url:
        db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
    
    try:
        conn = await asyncpg.connect(db_url)
        
        # Check which columns exist
        result = await conn.fetch('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'places'
        ''')
        existing_columns = {row['column_name'] for row in result}
        print('Existing columns:', sorted(existing_columns))
        
        # Define required columns from the model
        required_columns = {
            'postal_code': 'VARCHAR',
            'cross_street': 'VARCHAR', 
            'formatted_address': 'TEXT',
            'distance_meters': 'FLOAT',
            'venue_created_at': 'TIMESTAMP WITH TIME ZONE',
            'photo_url': 'VARCHAR',
            'additional_photos': 'JSONB'
        }
        
        # Add missing columns
        added_columns = []
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                print(f'Adding column: {column_name} {column_type}')
                await conn.execute(f'ALTER TABLE places ADD COLUMN {column_name} {column_type}')
                added_columns.append(column_name)
            else:
                print(f'Column {column_name} already exists')
        
        if added_columns:
            print(f'Successfully added columns: {added_columns}')
        else:
            print('All required columns already exist')
            
        return True
        
    except Exception as e:
        print(f'Error adding columns: {e}')
        return False
    finally:
        if 'conn' in locals():
            await conn.close()

def add_missing_columns_sync():
    """Add missing columns using SQLAlchemy (synchronous)"""
    # Get database URL from environment
    db_url = os.getenv('APP_DATABASE_URL')
    if not db_url:
        print("APP_DATABASE_URL not found")
        return False
    
    try:
        # Create engine and session
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Check which columns exist
        result = session.execute(text('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'places'
        '''))
        existing_columns = {row[0] for row in result}
        print('Existing columns:', sorted(existing_columns))
        
        # Define required columns from the model
        required_columns = {
            'postal_code': 'VARCHAR',
            'cross_street': 'VARCHAR', 
            'formatted_address': 'TEXT',
            'distance_meters': 'FLOAT',
            'venue_created_at': 'TIMESTAMP WITH TIME ZONE',
            'photo_url': 'VARCHAR',
            'additional_photos': 'JSONB'
        }
        
        # Add missing columns
        added_columns = []
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                print(f'Adding column: {column_name} {column_type}')
                session.execute(text(f'ALTER TABLE places ADD COLUMN {column_name} {column_type}'))
                added_columns.append(column_name)
            else:
                print(f'Column {column_name} already exists')
        
        session.commit()
        
        if added_columns:
            print(f'Successfully added columns: {added_columns}')
        else:
            print('All required columns already exist')
            
        return True
        
    except Exception as e:
        print(f'Error adding columns: {e}')
        session.rollback()
        return False
    finally:
        if 'session' in locals():
            session.close()
        if 'engine' in locals():
            engine.dispose()

if __name__ == "__main__":
    print("Starting database migration...")
    
    # Try async first, fallback to sync
    try:
        success = asyncio.run(add_missing_columns_async())
    except Exception as e:
        print(f"Async migration failed: {e}")
        print("Trying synchronous migration...")
        success = add_missing_columns_sync()
    
    if success:
        print("Migration completed successfully!")
        sys.exit(0)
    else:
        print("Migration failed!")
        sys.exit(1)
