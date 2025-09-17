#!/usr/bin/env python3
"""
Fix alembic version issue by inserting missing revision
"""
import os
import psycopg

def fix_alembic_version():
    # Get database URL from environment
    db_url = os.environ['APP_DATABASE_URL']

    # Convert asyncpg URL to psycopg URL for sync connection
    sync_db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

    try:
        # Connect to database
        with psycopg.connect(sync_db_url) as conn:
            with conn.cursor() as cur:
                # Check current alembic version
                cur.execute("SELECT version_num FROM alembic_version ORDER BY version_num;")
                current_versions = cur.fetchall()
                print(f"Current alembic versions: {current_versions}")

                # Check if our problematic revision exists
                missing_revision = '499278ad9251'
                if not any(missing_revision in str(v) for v in current_versions):
                    print(f"Missing revision {missing_revision} - inserting it")

                    # Insert the missing revision
                    cur.execute(
                        "INSERT INTO alembic_version (version_num) VALUES (%s) ON CONFLICT (version_num) DO NOTHING",
                        (missing_revision,)
                    )
                    conn.commit()
                    print(f"Successfully inserted revision {missing_revision}")
                else:
                    print(f"Revision {missing_revision} already exists")

                # Verify the fix
                cur.execute("SELECT version_num FROM alembic_version ORDER BY version_num;")
                final_versions = cur.fetchall()
                print(f"Final alembic versions: {final_versions}")

    except Exception as e:
        print(f"Error fixing alembic: {e}")
        return False

    return True

if __name__ == "__main__":
    success = fix_alembic_version()
    exit(0 if success else 1)