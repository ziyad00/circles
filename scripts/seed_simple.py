#!/usr/bin/env python3
"""
Simple seeding script that works in ECS container
"""
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON
import asyncio
import random
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
import os

# Database URL from environment
DATABASE_URL = os.getenv(
    "APP_DATABASE_URL", "postgresql+asyncpg://postgres:password@postgres:5432/circles")

# Create engine and session
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False)

# Simple models - just what we need

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

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    place_id = Column(Integer)
    rating = Column(Integer)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class Photo(Base):
    __tablename__ = "photos"
    id = Column(Integer, primary_key=True)
    review_id = Column(Integer)
    place_id = Column(Integer)
    url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


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

        # Create sample reviews and photos
        reviews_created = 0
        photos_created = 0
        
        # Sample photo URLs (using placeholder images)
        sample_photo_urls = [
            "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=800",  # cafe
            "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=800",  # restaurant
            "https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=800",  # coworking
            "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=800",  # park
            "https://images.unsplash.com/photo-1541961017774-22349e4a1262?w=800",  # gallery
            "https://images.unsplash.com/photo-1559329007-40df8a9345d8?w=800",  # cafe interior
            "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800",  # restaurant food
            "https://images.unsplash.com/photo-1524758631624-e2822e304c36?w=800",  # workspace
            "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800",  # outdoor
            "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800",  # modern space
        ]
        
        for place in places:
            # Each place gets 1-2 reviews with photos
            num_reviews = random.randint(1, 2)
            place_reviewers = random.sample(users, min(num_reviews, len(users)))
            
            for reviewer in place_reviewers:
                review = Review(
                    user_id=reviewer.id,
                    place_id=place.id,
                    rating=random.randint(3, 5),
                    content=random.choice([
                        "Amazing place with great atmosphere!",
                        "Highly recommend this spot.",
                        "Perfect for work and relaxation.",
                        "Love the ambiance and service.",
                        "Great location with excellent amenities.",
                        "One of my favorite places in the city."
                    ]),
                    created_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
                )
                session.add(review)
                reviews_created += 1
                
                # Add 1-3 photos per review
                num_photos = random.randint(1, 3)
                for _ in range(num_photos):
                    photo = Photo(
                        review_id=None,  # Will be set after review is committed
                        place_id=place.id,
                        url=random.choice(sample_photo_urls),
                        created_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
                    )
                    session.add(photo)
                    photos_created += 1
        
        await session.commit()
        
        # Update photos with review_ids
        from sqlalchemy import update
        reviews = await session.execute(select(Review))
        reviews_list = reviews.scalars().all()
        
        photos = await session.execute(select(Photo).where(Photo.review_id.is_(None)))
        photos_list = photos.scalars().all()
        
        # Assign photos to reviews (simple assignment)
        photos_per_review = len(photos_list) // len(reviews_list) if reviews_list else 0
        for i, review in enumerate(reviews_list):
            start_idx = i * photos_per_review
            end_idx = start_idx + photos_per_review
            for j in range(start_idx, min(end_idx, len(photos_list))):
                if j < len(photos_list):
                    photos_list[j].review_id = review.id
        
        await session.commit()
        print(f"✅ Created {reviews_created} reviews and {photos_created} photos")

        print("🎉 Seeding completed successfully!")
        print(
            f"📊 Summary: {len(users)} users, {len(places)} places, {checkins_created} check-ins, {reviews_created} reviews, {photos_created} photos")

if __name__ == "__main__":
    asyncio.run(seed_data())
