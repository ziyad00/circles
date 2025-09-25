"""
Comprehensive tests for Collections and Media endpoints
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import asyncio
from datetime import datetime, timedelta, timezone

from app.main import app
from app.database import get_db
from app.models import Base, User, UserCollection, UserCollectionPlace, Place, CheckIn, CheckInPhoto
from app.services.jwt_service import JWTService


# Test database setup
DATABASE_URL = "sqlite+aiosqlite:///./test.db"
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


@pytest.fixture(autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def test_user():
    """Create a test user"""
    async with AsyncSessionLocal() as session:
        user = User(
            phone="+1234567890",
            username="testuser",
            first_name="Test",
            last_name="User",
            is_verified=True,
            is_onboarded=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def test_place():
    """Create a test place"""
    async with AsyncSessionLocal() as session:
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
        return place


@pytest.fixture
async def auth_token(test_user):
    """Create authentication token for test user"""
    return JWTService.create_access_token({"sub": str(test_user.id), "phone": test_user.phone})


@pytest.mark.asyncio
async def test_create_collection():
    """Test collection creation endpoint"""
    async with AsyncSessionLocal() as session:
        # Create test user
        user = User(
            phone="+1234567890",
            username="testuser",
            first_name="Test",
            last_name="User",
            is_verified=True,
            is_onboarded=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        token = JWTService.create_access_token(
            {"sub": str(user.id), "phone": user.phone})

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/collections/",
            json={
                "name": "My Favorites",
                "description": "Places I love",
                "is_public": True
            },
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "My Favorites"
        assert data["description"] == "Places I love"
        assert data["is_public"] == True
        assert data["user_id"] == user.id


@pytest.mark.asyncio
async def test_list_empty_collections():
    """Test listing collections when user has none"""
    async with AsyncSessionLocal() as session:
        user = User(
            phone="+1234567890",
            username="testuser",
            first_name="Test",
            last_name="User",
            is_verified=True,
            is_onboarded=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        token = JWTService.create_access_token(
            {"sub": str(user.id), "phone": user.phone})

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/collections/",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []


@pytest.mark.asyncio
async def test_list_user_collections():
    """Test listing collections for a user"""
    async with AsyncSessionLocal() as session:
        # Create test user
        user = User(
            phone="+1234567890",
            username="testuser",
            first_name="Test",
            last_name="User",
            is_verified=True,
            is_onboarded=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # Create a collection
        collection = UserCollection(
            user_id=user.id,
            name="My Favorites",
            description="Places I love",
            is_public=True
        )
        session.add(collection)
        await session.commit()
        await session.refresh(collection)

        token = JWTService.create_access_token(
            {"sub": str(user.id), "phone": user.phone})

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/collections/",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == collection.id
        assert data[0]["name"] == "My Favorites"
        assert data[0]["user_id"] == user.id


@pytest.mark.asyncio
async def test_list_user_collections_legacy_endpoint():
    """Test the legacy collections endpoint (should work with new system)"""
    async with AsyncSessionLocal() as session:
        # Create test user
        user = User(
            phone="+1234567890",
            username="testuser",
            first_name="Test",
            last_name="User",
            is_verified=True,
            is_onboarded=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # Create a collection
        collection = UserCollection(
            user_id=user.id,
            name="My Favorites",
            description="Places I love",
            is_public=True
        )
        session.add(collection)
        await session.commit()
        await session.refresh(collection)

        token = JWTService.create_access_token(
            {"sub": str(user.id), "phone": user.phone})

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            f"/users/{user.id}/collections",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == collection.id
        assert data[0]["name"] == "My Favorites"


@pytest.mark.asyncio
async def test_get_user_media_empty():
    """Test user media endpoint when user has no media"""
    async with AsyncSessionLocal() as session:
        user = User(
            phone="+1234567890",
            username="testuser",
            first_name="Test",
            last_name="User",
            is_verified=True,
            is_onboarded=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        token = JWTService.create_access_token(
            {"sub": str(user.id), "phone": user.phone})

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            f"/users/{user.id}/media",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_user_media_with_checkins():
    """Test user media endpoint with check-in photos"""
    async with AsyncSessionLocal() as session:
        # Create test user
        user = User(
            phone="+1234567890",
            username="testuser",
            first_name="Test",
            last_name="User",
            is_verified=True,
            is_onboarded=True
        )
        session.add(user)

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
        await session.refresh(user)
        await session.refresh(place)

        # Create check-in with photo
        checkin = CheckIn(
            user_id=user.id,
            place_id=place.id,
            visibility="public",
            latitude=24.7876,
            longitude=46.6597
        )
        session.add(checkin)
        await session.commit()
        await session.refresh(checkin)

        photo = CheckInPhoto(
            check_in_id=checkin.id,
            photo_url="https://example.com/photo.jpg"
        )
        session.add(photo)
        await session.commit()

        token = JWTService.create_access_token(
            {"sub": str(user.id), "phone": user.phone})

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            f"/users/{user.id}/media",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["photo_url"] == "https://example.com/photo.jpg"
        assert data["total"] == 1


@pytest.mark.asyncio
async def test_integration_create_collection_and_get_media():
    """Integration test: create collection and verify it appears in user's collections"""
    async with AsyncSessionLocal() as session:
        # Create test user
        user = User(
            phone="+1234567890",
            username="testuser",
            first_name="Test",
            last_name="User",
            is_verified=True,
            is_onboarded=True
        )
        session.add(user)

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
        await session.refresh(user)
        await session.refresh(place)

        token = JWTService.create_access_token(
            {"sub": str(user.id), "phone": user.phone})

    # Test collection creation
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create collection
        response = await client.post(
            "/collections/",
            json={
                "name": "Coffee Places",
                "description": "My favorite coffee spots",
                "is_public": True
            },
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        collection_data = response.json()
        collection_id = collection_data["id"]

        # Verify collection appears in user's collections
        response = await client.get(
            "/collections/",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        collections = response.json()
        assert len(collections) == 1
        assert collections[0]["id"] == collection_id
        assert collections[0]["name"] == "Coffee Places"

        # Verify collection appears in legacy endpoint too
        response = await client.get(
            f"/users/{user.id}/collections",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        legacy_collections = response.json()
        assert len(legacy_collections) == 1
        assert legacy_collections[0]["id"] == collection_id
        assert legacy_collections[0]["name"] == "Coffee Places"


if __name__ == "__main__":
    # Run tests manually
    asyncio.run(test_create_collection())
    asyncio.run(test_list_empty_collections())
    asyncio.run(test_list_user_collections())
    asyncio.run(test_list_user_collections_legacy_endpoint())
    asyncio.run(test_get_user_media_empty())
    asyncio.run(test_get_user_media_with_checkins())
    asyncio.run(test_integration_create_collection_and_get_media())

    print("✅ All tests passed!")
