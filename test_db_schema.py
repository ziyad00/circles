import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
import os

async def check_db_schema():
    # Use the same database URL as the application
    db_url = os.getenv('APP_DATABASE_URL')
    if not db_url:
        print("❌ APP_DATABASE_URL not found")
        return
    
    engine = create_async_engine(db_url)
    
    try:
        async with engine.connect() as conn:
            print("✅ Connected to database")
            
            # Check if required tables exist
            tables_result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('dm_messages', 'dm_threads', 'dm_message_reactions', 'users')
                ORDER BY table_name
            """))
            tables = tables_result.fetchall()
            print(f"\n📋 Tables found: {[t[0] for t in tables]}")
            
            # Check dm_messages columns
            if any('dm_messages' in t[0] for t in tables):
                columns_result = await conn.execute(text("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns 
                    WHERE table_name = 'dm_messages' 
                    AND column_name IN ('id', 'thread_id', 'sender_id', 'text', 'created_at', 'deleted_at', 'reply_to_id', 'reply_to_text', 'photo_urls', 'video_urls', 'caption')
                    ORDER BY column_name
                """))
                columns = columns_result.fetchall()
                print(f"\n📝 DM Messages columns:")
                for col in columns:
                    print(f"  - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
            
            # Check if dm_message_reactions table exists
            reactions_result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'dm_message_reactions'
            """))
            if reactions_result.fetchone():
                print("✅ dm_message_reactions table exists")
            else:
                print("❌ dm_message_reactions table missing")
            
            # Try a simple query on dm_messages
            try:
                count_result = await conn.execute(text("SELECT COUNT(*) FROM dm_messages"))
                count = count_result.scalar()
                print(f"📊 DM Messages count: {count}")
            except Exception as e:
                print(f"❌ Error querying dm_messages: {e}")
            
            # Try the inbox query structure
            try:
                inbox_test = await conn.execute(text("""
                    SELECT COUNT(*) FROM dm_threads dt
                    JOIN dm_participant_states dps ON dps.thread_id = dt.id
                    WHERE dt.status = 'accepted'
                    AND (dt.user_a_id = 8 OR dt.user_b_id = 8)
                    LIMIT 1
                """))
                inbox_count = inbox_test.scalar()
                print(f"✅ Basic inbox query works: {inbox_count}")
            except Exception as e:
                print(f"❌ Inbox query error: {e}")
                
    except Exception as e:
        print(f"❌ Database connection error: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_db_schema())
