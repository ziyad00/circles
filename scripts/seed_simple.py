#!/usr/bin/env python3
"""
Simple seeding script that works in ECS container
"""
import asyncio
import random
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
import os

# Database URL from environment
DATABASE_URL = os.getenv("APP_DATABASE_URL", "postgresql+asyncpg://postgres:password@postgres:5432/circles")

# Create engine and session
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Simple models - just what we need
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    phone = Column(String, unique=True)
    username = Column(String)
    name = Column(String)
    is_verified = Column(Boolean, default=True)
    dm_privacy = Column(String, default="everyone")
    checkins_default_visibility = Column(String, default="public")
    collections_default_visibility = Column(String, default="public")
    created_at = Column(DateTime, default=datetime.utcnow)

class Place(Base):
    __tablename__ = "places"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    address = Column(String)
    city = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    categories = Column(String)
    rating = Column(Float)
    place_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class CheckIn(Base):
    __tablename__ = "check_ins"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    place_id = Column(Integer)
    note = Column(String)
    visibility = Column(String, default="public")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)

async def seed_data():
    """Seed the database with sample data"""
    print("🚀 Starting simple data seeding...")
    
    async with AsyncSessionLocal() as session:
        # Check if we already have data
        existing_users = await session.execute(select(User))
        if len(existing_users.scalars().all()) >= 5:
            print("⚠️  Database already has users, skipping seeding")
            return
        
        # Create sample users
        users_data = [
            {"phone": "+15551234567", "username": "alice_j", "name": "Alice Johnson"},
            {"phone": "+15551234568", "username": "bob_s", "name": "Bob Smith"},
            {"phone": "+15551234569", "username": "charlie_b", "name": "Charlie Brown"},
            {"phone": "+15551234570", "username": "diana_p", "name": "Diana Prince"},
            {"phone": "+15551234571", "username": "eve_w", "name": "Eve Wilson"},
        ]
        
        users = []
        for user_data in users_data:
            user = User(**user_data)
            session.add(user)
            users.append(user)
        
        await session.commit()
        print(f"✅ Created {len(users)} users")
        
        # Create sample places with some having amenities metadata
        places_data = [
            {
                "name": "Central Park Coffee",
                "address": "123 Main St, Riyadh",
                "city": "Riyadh",
                "latitude": 24.7136,
                "longitude": 46.6753,
                "categories": "cafe",
                "rating": 4.5,
                "place_metadata": {
                    "amenities": {"wifi": True, "outdoor_seating": False, "family_friendly": True}
                }
            },
            {
                "name": "Downtown Pizza Palace", 
                "address": "456 King Fahd Rd, Riyadh",
                "city": "Riyadh",
                "latitude": 24.7205,
                "longitude": 46.6759,
                "categories": "restaurant",
                "rating": 4.2,
                "place_metadata": {
                    "amenities": {"wifi": True, "parking": True, "delivery": True, "family_friendly": True}
                }
            },
            {
                "name": "Tech Hub Workspace",
                "address": "789 Olaya St, Riyadh", 
                "city": "Riyadh",
                "latitude": 24.7645,
                "longitude": 46.6741,
                "categories": "coworking",
                "rating": 4.7,
                "place_metadata": {
                    "amenities": {"wifi": True, "parking": True, "wheelchair_accessible": True}
                }
            },
            {
                "name": "Green Gardens Park",
                "address": "321 Prince Mohammed Bin Abdulaziz Rd, Riyadh",
                "city": "Riyadh", 
                "latitude": 24.7580,
                "longitude": 46.6776,
                "categories": "park",
                "rating": 4.8,
                "place_metadata": {
                    "amenities": {"family_friendly": True, "outdoor_seating": True, "parking": True}
                }
            },
            {
                "name": "Art Gallery Modern",
                "address": "654 Tahlia St, Riyadh",
                "city": "Riyadh",
                "latitude": 24.7614,
                "longitude": 46.6776,
                "categories": "museum",
                "rating": 4.6,
                "place_metadata": {
                    "amenities": {"wifi": False, "wheelchair_accessible": True, "parking": True}
                }
            }
        ]
        
        places = []
        for place_data in places_data:
            place = Place(**place_data)
            session.add(place)
            places.append(place)
            
        await session.commit()
        print(f"✅ Created {len(places)} places with amenities")
        
        # Create sample check-ins
        checkins_created = 0
        for user in users:
            # Each user checks into 2-3 random places
            user_places = random.sample(places, random.randint(2, 3))
            for place in user_places:
                checkin = CheckIn(
                    user_id=user.id,
                    place_id=place.id,
                    note=random.choice([
                        "Great place!", "Love the atmosphere", "Highly recommend",
                        "Perfect spot", "Amazing experience", None
                    ]),
                    visibility="public",
                    created_at=datetime.utcnow() - timedelta(hours=random.randint(1, 48)),
                    expires_at=datetime.utcnow() + timedelta(hours=24)
                )
                session.add(checkin)
                checkins_created += 1
        
        await session.commit()
        print(f"✅ Created {checkins_created} check-ins")
        
        print("🎉 Seeding completed successfully!")
        print(f"📊 Summary: {len(users)} users, {len(places)} places, {checkins_created} check-ins")

if __name__ == "__main__":
    asyncio.run(seed_data())
