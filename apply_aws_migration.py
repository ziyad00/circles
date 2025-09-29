#!/usr/bin/env python3
"""
Script to apply the updated_at field migration to AWS database
"""
import os
import sys
import sqlalchemy as sa
from sqlalchemy import create_engine, text

# AWS Database connection
AWS_DATABASE_URL = os.getenv('AWS_DATABASE_URL')

def apply_migration():
    """Apply the updated_at field to dm_messages table"""
    if not AWS_DATABASE_URL:
        print("❌ AWS_DATABASE_URL environment variable not set")
        return False

    try:
        engine = create_engine(AWS_DATABASE_URL)

        with engine.connect() as conn:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT COUNT(*) as count
                FROM information_schema.columns
                WHERE table_name = 'dm_messages'
                AND column_name = 'updated_at'
            """))

            if result.fetchone()[0] > 0:
                print("✅ updated_at column already exists in dm_messages table")
                return True

            # Add the updated_at column
            print("🔧 Adding updated_at column to dm_messages table...")
            conn.execute(text("""
                ALTER TABLE dm_messages
                ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE
            """))

            # Update existing records to have updated_at = created_at
            print("🔧 Setting updated_at for existing records...")
            conn.execute(text("""
                UPDATE dm_messages
                SET updated_at = created_at
                WHERE updated_at IS NULL
            """))

            conn.commit()
            print("✅ Migration applied successfully!")
            return True

    except Exception as e:
        print(f"❌ Error applying migration: {e}")
        return False

if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)