#!/usr/bin/env python3
"""
Sample Data Population Script for Circles Application

This script populates the database with sample data for development and testing.
It creates users, places, check-ins, collections, DMs, and other entities to
demonstrate the full functionality of the Circles application.

Usage:
    python scripts/populate_sample_data.py
"""

import sys
import os

# Ensure project root is importable before importing app.* modules
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# Also try current working directory (for ECS container)
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

from sqlalchemy.orm import selectinload
from sqlalchemy import select
from app.services.jwt_service import JWTService
from app.services.storage import StorageService
from app.models import (
    User, Place, CheckIn, CheckInCollection, CheckInCollectionItem, CheckInPhoto,
    DMThread, DMMessage, DMParticipantState, Follow, UserInterest,
    NotificationPreference, SupportTicket, Activity, CheckInComment,
    CheckInLike, OTPCode
)
from app.database import AsyncSessionLocal
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
import random


class SampleDataPopulator:
    def __init__(self):
        self.storage_service = StorageService()
        self.jwt_service = JWTService()

        # Sample data arrays
        self.sample_names = [
            "Alice Johnson", "Bob Smith", "Charlie Brown", "Diana Prince",
            "Eve Wilson", "Frank Miller", "Grace Lee", "Henry Davis",
            "Iris Chen", "Jack Taylor", "Kate Williams", "Liam O'Connor",
            "Maya Patel", "Noah Rodriguez", "Olivia Garcia", "Paul Kim",
            "Quinn Anderson", "Rachel Green", "Sam Thompson", "Tina Turner"
        ]

        self.sample_emails = [
            "alice@example.com", "bob@example.com", "charlie@example.com",
            "diana@example.com", "eve@example.com", "frank@example.com",
            "grace@example.com", "henry@example.com", "iris@example.com",
            "jack@example.com", "kate@example.com", "liam@example.com",
            "maya@example.com", "noah@example.com", "olivia@example.com",
            "paul@example.com", "quinn@example.com", "rachel@example.com",
            "sam@example.com", "tina@example.com"
        ]

        self.sample_usernames = [
            "alice_j", "bobsmith", "charlieb", "diana_p", "eve_w",
            "frankm", "gracelee", "henryd", "irischen", "jackt",
            "katew", "liamoc", "mayap", "noahr", "oliviag",
            "paulk", "quinna", "rachelg", "samt", "tinat"
        ]

        self.sample_places = [
            {
                "name": "Central Park Coffee",
                "address": "123 Main St, New York, NY 10001",
                "latitude": 40.7589,
                "longitude": -73.9851,
                "category": "Coffee Shop",
                "rating": 4.5
            },
            {
                "name": "Downtown Pizza Palace",
                "address": "456 Broadway, New York, NY 10013",
                "latitude": 40.7205,
                "longitude": -74.0059,
                "category": "Restaurant",
                "rating": 4.2
            },
            {
                "name": "Tech Hub Workspace",
                "address": "789 5th Ave, New York, NY 10065",
                "latitude": 40.7645,
                "longitude": -73.9741,
                "category": "Coworking Space",
                "rating": 4.7
            },
            {
                "name": "Green Gardens Park",
                "address": "321 Park Ave, New York, NY 10022",
                "latitude": 40.7580,
                "longitude": -73.9776,
                "category": "Park",
                "rating": 4.8
            },
            {
                "name": "Art Gallery Modern",
                "address": "654 Madison Ave, New York, NY 10021",
                "latitude": 40.7614,
                "longitude": -73.9776,
                "category": "Museum",
                "rating": 4.6
            },
            {
                "name": "Fitness First Gym",
                "address": "987 Lexington Ave, New York, NY 10065",
                "latitude": 40.7645,
                "longitude": -73.9741,
                "category": "Gym",
                "rating": 4.3
            },
            {
                "name": "Bookworm Library",
                "address": "147 3rd Ave, New York, NY 10003",
                "latitude": 40.7328,
                "longitude": -73.9871,
                "category": "Library",
                "rating": 4.4
            },
            {
                "name": "Music Studio Central",
                "address": "258 6th Ave, New York, NY 10014",
                "latitude": 40.7359,
                "longitude": -74.0026,
                "category": "Music Venue",
                "rating": 4.1
            }
        ]

        self.sample_collections = [
            "Favorite Coffee Shops",
            "Best Pizza Places",
            "Workout Spots",
            "Art & Culture",
            "Hidden Gems",
            "Date Night Places",
            "Quick Lunch Spots",
            "Weekend Hangouts"
        ]

        self.sample_interests = [
            "Coffee", "Food", "Fitness", "Art", "Music", "Books",
            "Technology", "Travel", "Photography", "Sports",
            "Cooking", "Gaming", "Movies", "Fashion", "Nature"
        ]

    async def create_users(self, session) -> List[User]:
        """Create sample users with various settings and interests."""
        print("Creating sample users...")
        users = []

        for i in range(20):
            # Deterministic sample phone per user
            phone = f"+1555{(1000000 + i):07d}"
            # Check if user already exists by phone
            existing_user_res = await session.execute(
                select(User).where(User.phone == phone)
            )
            existing_user = existing_user_res.scalar_one_or_none()

            if existing_user:
                users.append(existing_user)
                continue

            user = User(
                phone=phone,
                username=self.sample_usernames[i],
                name=self.sample_names[i],
                dm_privacy=random.choice(["everyone", "followers", "no_one"]),
                checkins_default_visibility=random.choice(
                    ["public", "friends", "private"]),
                collections_default_visibility=random.choice(
                    ["public", "friends", "private"]),
                is_verified=random.choice([True, False]),
                created_at=datetime.utcnow() - timedelta(days=random.randint(1, 365))
            )
            session.add(user)
            users.append(user)

        await session.commit()

        # Create user interests
        for user in users:
            num_interests = random.randint(2, 5)
            user_interests = random.sample(
                self.sample_interests, num_interests)
            for interest_name in user_interests:
                interest = UserInterest(user_id=user.id, name=interest_name)
                session.add(interest)

        # Create notification preferences
        for user in users:
            pref = NotificationPreference(
                user_id=user.id,
                dm_messages=random.choice([True, False]),
                dm_requests=random.choice([True, False]),
                follows=random.choice([True, False]),
                likes=random.choice([True, False]),
                comments=random.choice([True, False]),
                activity_summary=random.choice([True, False]),
                marketing=random.choice([True, False])
            )
            session.add(pref)

        await session.commit()
        print(f"Created {len(users)} users with interests and preferences")
        return users

    async def create_places(self, session) -> List[Place]:
        """Create sample places."""
        print("Creating sample places...")
        places = []

        for place_data in self.sample_places:
            place = Place(
                name=place_data["name"],
                address=place_data["address"],
                latitude=place_data["latitude"],
                longitude=place_data["longitude"],
                category=place_data["category"],
                rating=place_data["rating"],
                total_reviews=random.randint(10, 500),
                created_at=datetime.utcnow() - timedelta(days=random.randint(1, 365))
            )
            session.add(place)
            places.append(place)

        await session.commit()
        # Backfill city for Riyadh bounding box if missing
        updated = 0
        for p in places:
            if getattr(p, 'city', None) in (None, '') and getattr(p, 'latitude', None) is not None and getattr(p, 'longitude', None) is not None:
                lat, lon = p.latitude, p.longitude
                if 24.3 <= lat <= 25.2 and 46.2 <= lon <= 47.3:
                    p.city = "Riyadh"
                    updated += 1
        if updated:
            await session.commit()
        print(
            f"Created {len(places)} places (city backfilled for Riyadh: {updated})")
        return places

    async def create_follows(self, session, users: List[User]):
        """Create follow relationships between users."""
        print("Creating follow relationships...")
        follows_created = 0

        for user in users:
            # Each user follows 3-8 other random users
            num_follows = random.randint(3, 8)
            follow_candidates = [u for u in users if u.id != user.id]
            followed_users = random.sample(
                follow_candidates, min(num_follows, len(follow_candidates)))

            for followed_user in followed_users:
                # Check if follow already exists
                existing_follow = await session.execute(
                    select(Follow).where(
                        Follow.follower_id == user.id,
                        Follow.followee_id == followed_user.id
                    )
                )
                if not existing_follow.scalar_one_or_none():
                    follow = Follow(
                        follower_id=user.id,
                        followee_id=followed_user.id,
                        created_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
                    )
                    session.add(follow)
                    follows_created += 1

        await session.commit()
        print(f"Created {follows_created} follow relationships")

    async def create_collections(self, session, users: List[User], places: List[Place]):
        """Create sample collections for users."""
        print("Creating sample collections...")
        collections_created = 0

        for user in users:
            # Each user has 2-4 collections
            num_collections = random.randint(2, 4)
            collection_names = random.sample(
                self.sample_collections, num_collections)

            for collection_name in collection_names:
                collection = CheckInCollection(
                    name=collection_name,
                    user_id=user.id,
                    visibility=user.collections_default_visibility,
                    created_at=datetime.utcnow() - timedelta(days=random.randint(1, 90))
                )
                session.add(collection)
                collections_created += 1

        await session.commit()

        # Add places to collections
        collections = await session.execute(select(CheckInCollection))
        collections = collections.scalars().all()

        for collection in collections:
            # Add 3-8 random places to each collection
            num_places = random.randint(3, 8)
            collection_places = random.sample(
                places, min(num_places, len(places)))

            # Get some check-ins for this user to add to the collection
            user_checkins = await session.execute(
                select(CheckIn).where(CheckIn.user_id ==
                                      collection.user_id).limit(5)
            )
            user_checkins = user_checkins.scalars().all()

            for checkin in user_checkins:
                item = CheckInCollectionItem(
                    collection_id=collection.id,
                    check_in_id=checkin.id
                )
                session.add(item)

        await session.commit()
        print(f"Created {collections_created} collections with items")

    async def create_checkins(self, session, users: List[User], places: List[Place]):
        """Create sample check-ins."""
        print("Creating sample check-ins...")
        checkins_created = 0

        for user in users:
            # Each user has 5-15 check-ins
            num_checkins = random.randint(5, 15)
            user_places = random.sample(places, min(num_checkins, len(places)))

            for i, place in enumerate(user_places):
                checkin_time = datetime.utcnow() - timedelta(
                    days=random.randint(1, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )

                checkin = CheckIn(
                    user_id=user.id,
                    place_id=place.id,
                    note=random.choice([
                        "Great place!",
                        "Amazing atmosphere",
                        "Highly recommend",
                        "Perfect for work",
                        "Love this spot",
                        "Must visit again",
                        "Excellent service",
                        "Beautiful location",
                        None, None, None  # Some check-ins without notes
                    ]),
                    visibility=user.checkins_default_visibility,
                    created_at=checkin_time
                )
                session.add(checkin)
                checkins_created += 1

        await session.commit()
        print(f"Created {checkins_created} check-ins")

    async def create_dm_threads(self, session, users: List[User]):
        """Create sample DM threads and messages."""
        print("Creating sample DM threads...")
        threads_created = 0
        messages_created = 0

        # Create some DM threads between users
        for i in range(len(users) // 2):
            user1 = users[i * 2]
            user2 = users[i * 2 + 1] if i * 2 + 1 < len(users) else users[0]

            # Check if thread already exists
            existing_thread = await session.execute(
                select(DMThread).where(
                    (DMThread.user1_id == user1.id and DMThread.user2_id == user2.id) or
                    (DMThread.user1_id == user2.id and DMThread.user2_id == user1.id)
                )
            )

            if not existing_thread.scalar_one_or_none():
                thread = DMThread(
                    user1_id=user1.id,
                    user2_id=user2.id,
                    created_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
                )
                session.add(thread)
                threads_created += 1

        await session.commit()

        # Add messages to threads
        threads = await session.execute(select(DMThread))
        threads = threads.scalars().all()

        sample_messages = [
            "Hey! How are you doing?",
            "Want to grab coffee sometime?",
            "Did you check out that new place?",
            "Great seeing you today!",
            "Thanks for the recommendation",
            "Let's meet up soon",
            "How was your weekend?",
            "That place was amazing!",
            "We should go there again",
            "Have you been to the new restaurant?"
        ]

        for thread in threads:
            # Add 3-8 messages to each thread
            num_messages = random.randint(3, 8)

            for i in range(num_messages):
                message_time = thread.created_at + timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )

                sender_id = thread.user1_id if i % 2 == 0 else thread.user2_id
                message = DMMessage(
                    thread_id=thread.id,
                    sender_id=sender_id,
                    content=random.choice(sample_messages),
                    created_at=message_time
                )
                session.add(message)
                messages_created += 1

        await session.commit()
        print(
            f"Created {threads_created} DM threads with {messages_created} messages")

    async def create_activities(self, session, users: List[User], places: List[Place]):
        """Create sample activities for the activity feed."""
        print("Creating sample activities...")
        activities_created = 0

        for user in users:
            # Create 5-10 activities per user
            num_activities = random.randint(5, 10)

            for _ in range(num_activities):
                activity_time = datetime.utcnow() - timedelta(
                    days=random.randint(1, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )

                activity_type = random.choice(
                    ["checkin", "follow", "collection_created"])

                if activity_type == "checkin":
                    place = random.choice(places)
                    activity = Activity(
                        user_id=user.id,
                        activity_type="checkin",
                        activity_data=f'{{"place_name": "{place.name}", "place_id": {place.id}}}',
                        created_at=activity_time
                    )
                elif activity_type == "follow":
                    # Find a random user to follow
                    other_users = [u for u in users if u.id != user.id]
                    if other_users:
                        followed_user = random.choice(other_users)
                        activity = Activity(
                            user_id=user.id,
                            activity_type="follow",
                            activity_data=f'{{"followed_user_name": "{followed_user.name}", "followed_user_id": {followed_user.id}}}',
                            created_at=activity_time
                        )
                    else:
                        continue
                else:  # collection_created
                    activity = Activity(
                        user_id=user.id,
                        activity_type="collection_created",
                        activity_data=f'{{"collection_name": "{random.choice(self.sample_collections)}"}}',
                        created_at=activity_time
                    )

                session.add(activity)
                activities_created += 1

        await session.commit()
        print(f"Created {activities_created} activities")

    async def create_support_tickets(self, session, users: List[User]):
        """Create sample support tickets."""
        print("Creating sample support tickets...")
        tickets_created = 0

        sample_issues = [
            "App not working properly",
            "Can't upload photos",
            "Location services not working",
            "Account verification issue",
            "Payment problem",
            "Bug report",
            "Feature request",
            "Privacy concern"
        ]

        for user in users:
            # 20% chance of having a support ticket
            if random.random() < 0.2:
                ticket = SupportTicket(
                    user_id=user.id,
                    subject=random.choice(sample_issues),
                    message=f"User {user.name} reported: {random.choice(sample_issues)}",
                    status=random.choice(
                        ["open", "in_progress", "resolved", "closed"]),
                    created_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
                )
                session.add(ticket)
                tickets_created += 1

        await session.commit()
        print(f"Created {tickets_created} support tickets")

    async def create_checkin_comments_and_likes(self, session, users: List[User]):
        """Create sample comments and likes on check-ins."""
        print("Creating sample check-in interactions...")

        # Get all check-ins
        checkins = await session.execute(select(CheckIn))
        checkins = checkins.scalars().all()

        comments_created = 0
        likes_created = 0

        for checkin in checkins:
            # 30% chance of having comments
            if random.random() < 0.3:
                num_comments = random.randint(1, 3)
                comment_users = random.sample(
                    users, min(num_comments, len(users)))

                for comment_user in comment_users:
                    if comment_user.id != checkin.user_id:  # Don't comment on own check-in
                        comment = CheckInComment(
                            check_in_id=checkin.id,
                            user_id=comment_user.id,
                            content=random.choice([
                                "Looks great!",
                                "I love this place too!",
                                "Thanks for sharing",
                                "Will check it out",
                                "Amazing spot!",
                                "Been there, it's awesome"
                            ]),
                            created_at=checkin.created_at + timedelta(
                                hours=random.randint(1, 24),
                                minutes=random.randint(0, 59)
                            )
                        )
                        session.add(comment)
                        comments_created += 1

            # 50% chance of having likes
            if random.random() < 0.5:
                num_likes = random.randint(1, 5)
                like_users = random.sample(users, min(num_likes, len(users)))

                for like_user in like_users:
                    if like_user.id != checkin.user_id:  # Don't like own check-in
                        # Check if like already exists
                        existing_like = await session.execute(
                            select(CheckInLike).where(
                                CheckInLike.check_in_id == checkin.id,
                                CheckInLike.user_id == like_user.id
                            )
                        )

                        if not existing_like.scalar_one_or_none():
                            like = CheckInLike(
                                check_in_id=checkin.id,
                                user_id=like_user.id,
                                created_at=checkin.created_at + timedelta(
                                    hours=random.randint(1, 24),
                                    minutes=random.randint(0, 59)
                                )
                            )
                            session.add(like)
                            likes_created += 1

        await session.commit()
        print(f"Created {comments_created} comments and {likes_created} likes")

    async def populate_database(self):
        """Main method to populate the database with all sample data."""
        print("Starting database population...")

        async with AsyncSessionLocal() as session:
            try:
                # Check if data already exists
                existing_users = await session.execute(select(User))
                existing_users = existing_users.scalars().all()

                if len(existing_users) >= 10:  # If we already have significant data
                    print(
                        "⚠️  Database already contains sample data. Skipping population.")
                    print(f"📊 Current data:")
                    print(f"   - Users: {len(existing_users)}")

                    # Get counts of other entities
                    existing_places = await session.execute(select(Place))
                    existing_places = existing_places.scalars().all()
                    print(f"   - Places: {len(existing_places)}")

                    existing_checkins = await session.execute(select(CheckIn))
                    existing_checkins = existing_checkins.scalars().all()
                    print(f"   - Check-ins: {len(existing_checkins)}")

                    print("✅ Database is ready for testing!")
                    return

                # Create all entities
                users = await self.create_users(session)
                places = await self.create_places(session)

                # Create relationships and interactions
                await self.create_follows(session, users)
                await self.create_collections(session, users, places)
                await self.create_checkins(session, users, places)
                await self.create_dm_threads(session, users)
                await self.create_activities(session, users, places)
                await self.create_support_tickets(session, users)
                await self.create_checkin_comments_and_likes(session, users)

                print("\n✅ Database population completed successfully!")
                print(f"📊 Summary:")
                print(f"   - Users: {len(users)}")
                print(f"   - Places: {len(places)}")
                print(f"   - Collections: {len(self.sample_collections)}")
                print(f"   - Sample data ready for testing!")

            except Exception as e:
                print(f"❌ Error populating database: {e}")
                await session.rollback()
                raise


async def main():
    """Main entry point."""
    print("🚀 Circles Sample Data Population Script")
    print("=" * 50)

    populator = SampleDataPopulator()
    await populator.populate_database()

    print("\n🎉 Sample data has been created!")
    print("You can now test the application with realistic data.")
    print("\nAccess the API at: http://localhost:8000/docs")


if __name__ == "__main__":
    asyncio.run(main())
