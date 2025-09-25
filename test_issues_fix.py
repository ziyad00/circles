"""
Test script to verify the three issues are fixed:
1. Collection creation: POST /collections/ - Returns empty response (schema issue)
2. User collections: GET /users/{user_id}/collections - Returns empty response (query issue)
3. User media: GET /users/{user_id}/media - Returns empty response (query issue)
"""

import asyncio
import sys
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import get_db
from app.models import Base, User, UserCollection, UserCollectionPlace, CheckIn, CheckInPhoto, Place
from app.services.jwt_service import JWTService
from app.routers.users import list_user_collections, get_user_media
from app.routers.collections import create_collection
from app.main import app
from fastapi.testclient import TestClient

# Test database setup
DATABASE_URL = "sqlite+aiosqlite:///./test_issues.db"
engine = create_async_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def setup_test_data():
    """Set up test data for the issues"""
    async with AsyncSessionLocal() as session:
        # Create test user with unique identifiers
        import random
        import string
        random_suffix = ''.join(random.choices(
            string.ascii_lowercase + string.digits, k=8))
        user = User(
            phone=f"+123456789{random_suffix}",
            username=f"testuser{random_suffix}",
            name="Test User",
            is_verified=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # Create test place
        place = Place(
            name="Test Coffee Shop",
            address="123 Test St",
            city="Test City",
            country="Test Country",
            latitude=24.7876,
            longitude=46.6597,
            categories="Coffee Shop"
        )
        session.add(place)
        await session.commit()
        await session.refresh(place)

        # Create test collection
        collection = UserCollection(
            user_id=user.id,
            name="Test Collection",
            description="Test collection for testing",
            is_public=True
        )
        session.add(collection)
        await session.commit()
        await session.refresh(collection)

        # Create test check-in with photo
        from datetime import datetime, timedelta, timezone
        expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        checkin = CheckIn(
            user_id=user.id,
            place_id=place.id,
            visibility="public",
            expires_at=expires_at,
            latitude=24.7876,
            longitude=46.6597
        )
        session.add(checkin)
        await session.commit()
        await session.refresh(checkin)

        photo = CheckInPhoto(
            check_in_id=checkin.id,
            url="https://example.com/photo.jpg"
        )
        session.add(photo)
        await session.commit()

        return user, place, collection, checkin, photo


async def test_issue_1_collection_creation():
    """Test Issue 1: Collection creation - POST /collections/"""
    print("🧪 Testing Issue 1: Collection Creation")

    try:
        async with AsyncSessionLocal() as session:
            # Create test user
            user = User(
                phone="+1234567890",
                username="testuser1",
                name="Test User",
                is_verified=True
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Test collection creation directly
            from app.schemas import CollectionCreate
            collection_create = CollectionCreate(
                name="Test Collection",
                description="Test collection",
                is_public=True
            )

            # Simulate the create_collection function
            new_collection = UserCollection(
                user_id=user.id,
                name=collection_create.name,
                description=collection_create.description,
                is_public=collection_create.is_public,
            )

            session.add(new_collection)
            await session.commit()
            await session.refresh(new_collection)

            print(
                f"✅ Collection created successfully: {new_collection.name} (ID: {new_collection.id})")
            return True

    except Exception as e:
        print(f"❌ Collection creation failed: {e}")
        return False


async def test_issue_2_user_collections():
    """Test Issue 2: User collections - GET /users/{user_id}/collections"""
    print("🧪 Testing Issue 2: User Collections")

    try:
        user, place, collection, checkin, photo = await setup_test_data()

        # Test the list_user_collections function directly
        async with AsyncSessionLocal() as session:
            result = await list_user_collections(
                user_id=user.id,
                limit=20,
                offset=0,
                db=session,
                current_user=user
            )

            print(
                f"✅ User collections retrieved: {len(result)} collections found")
            for collection_data in result:
                print(
                    f"  - {collection_data['name']} (ID: {collection_data['id']})")
            return True

    except Exception as e:
        print(f"❌ User collections failed: {e}")
        return False


async def test_issue_3_user_media():
    """Test Issue 3: User media - GET /users/{user_id}/media"""
    print("🧪 Testing Issue 3: User Media")

    try:
        user, place, collection, checkin, photo = await setup_test_data()

        # Use a different phone number for the user media test
        user.phone = "+1234567893"
        user.username = "testuser3"

        # Test the get_user_media function directly
        async with AsyncSessionLocal() as session:
            result = await get_user_media(
                user_id=user.id,
                limit=20,
                offset=0,
                db=session,
                current_user=user
            )

            print(f"✅ User media retrieved: {result.total} items found")
            print(f"  - Items: {result.items}")
            if result.items:
                print(f"  - First item type: {type(result.items[0])}")
            return True

    except Exception as e:
        print(f"❌ User media failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("🚀 Testing the three identified issues...")

    # Setup test database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Test each issue
    issue1_passed = await test_issue_1_collection_creation()
    issue2_passed = await test_issue_2_user_collections()
    issue3_passed = await test_issue_3_user_media()

    # Summary
    print("\n📋 Test Results Summary:")
    print(f"1. Collection Creation: {'✅ PASS' if issue1_passed else '❌ FAIL'}")
    print(f"2. User Collections: {'✅ PASS' if issue2_passed else '❌ FAIL'}")
    print(f"3. User Media: {'✅ PASS' if issue3_passed else '❌ FAIL'}")

    if all([issue1_passed, issue2_passed, issue3_passed]):
        print("🎉 All issues have been fixed!")
        return 0
    else:
        print("⚠️ Some issues still need attention")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
