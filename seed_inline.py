#!/usr/bin/env python3
"""Inline seeding script that works in ECS"""
import asyncio
import os
import json
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

async def seed_data():
    print("🚀 Starting inline seeding...")
    
    # Create engine
    engine = create_async_engine(os.getenv("APP_DATABASE_URL"))
    Session = sessionmaker(engine, class_=AsyncSession)
    
    async with Session() as s:
        # Create 5 test users
        users = [
            ("+15550000001", "alice_test", "Alice Test"),
            ("+15550000002", "bob_test", "Bob Test"), 
            ("+15550000003", "charlie_test", "Charlie Test"),
            ("+15550000004", "diana_test", "Diana Test"),
            ("+15550000005", "eve_test", "Eve Test")
        ]
        
        for phone, username, name in users:
            await s.execute(text("""
                INSERT INTO users(phone, username, name, is_verified, dm_privacy, checkins_default_visibility, collections_default_visibility)
                VALUES(:phone, :username, :name, true, 'everyone', 'public', 'public')
                ON CONFLICT(phone) DO NOTHING
            """), {"phone": phone, "username": username, "name": name})
        
        print("✅ Created test users")
        
        # Create test places with amenities
        places = [
            ("Riyadh Central Cafe", "Downtown Riyadh", "Riyadh", 24.7136, 46.6753, "cafe", 4.5,
             json.dumps({"amenities": {"wifi": True, "outdoor_seating": False, "family_friendly": True, "parking": True}})),
            ("King Fahd Pizza", "King Fahd Road", "Riyadh", 24.7205, 46.6759, "restaurant", 4.2,
             json.dumps({"amenities": {"wifi": True, "parking": True, "delivery": True, "takeout": True}})),
            ("Olaya Workspace", "Olaya Street", "Riyadh", 24.7645, 46.6741, "coworking", 4.7,
             json.dumps({"amenities": {"wifi": True, "parking": True, "wheelchair_accessible": True}})),
            ("Prince Mohammed Park", "Prince Mohammed Bin Abdulaziz Rd", "Riyadh", 24.7580, 46.6776, "park", 4.8,
             json.dumps({"amenities": {"family_friendly": True, "outdoor_seating": True, "parking": True}}))
        ]
        
        for name, addr, city, lat, lng, cat, rating, metadata in places:
            await s.execute(text("""
                INSERT INTO places(name, address, city, latitude, longitude, categories, rating, place_metadata, created_at)
                VALUES(:name, :addr, :city, :lat, :lng, :cat, :rating, :metadata::json, :created_at)
                ON CONFLICT DO NOTHING
            """), {
                "name": name, "addr": addr, "city": city, "lat": lat, "lng": lng, 
                "cat": cat, "rating": rating, "metadata": metadata, "created_at": datetime.utcnow()
            })
        
        print("✅ Created test places with amenities")
        
        # Create some check-ins
        await s.execute(text("""
            INSERT INTO check_ins(user_id, place_id, note, visibility, created_at, expires_at)
            SELECT u.id, p.id, 'Great place!', 'public', :created_at, :expires_at
            FROM users u, places p 
            WHERE u.phone = '+15550000001' AND p.name = 'Riyadh Central Cafe'
            ON CONFLICT DO NOTHING
        """), {
            "created_at": datetime.utcnow() - timedelta(hours=2),
            "expires_at": datetime.utcnow() + timedelta(hours=22)
        })
        
        print("✅ Created test check-ins")
        
        await s.commit()
        print("🎉 Seeding completed successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())
