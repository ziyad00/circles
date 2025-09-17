import os

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select

TEST_DB = "collections_test.db"
os.environ.setdefault("APP_DATABASE_URL", f"sqlite+aiosqlite:///{TEST_DB}")
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

from app.main import app  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Place,
    SavedPlace,
    User,
    UserCollection,
    UserCollectionPlace,
)
from app.services.jwt_service import JWTService  # noqa: E402


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers():
    async with AsyncSessionLocal() as session:
        user = User(
            phone="+1112223333",
            username="collector",
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = JWTService.create_token(user.id)
        yield {"Authorization": f"Bearer {token}"}, user.id


async def _create_place() -> int:
    async with AsyncSessionLocal() as session:
        place = Place(
            name="Sync Spot",
            latitude=1.0,
            longitude=1.0,
        )
        session.add(place)
        await session.commit()
        await session.refresh(place)
        return place.id


@pytest.mark.asyncio
async def test_saved_place_syncs_collections(client, auth_headers):
    headers, user_id = auth_headers
    place_id = await _create_place()

    resp = await client.post(
        "/places/saved",
        json={"place_id": place_id, "list_name": " Weekend "},
        headers=headers,
    )
    assert resp.status_code == 200
    saved_body = resp.json()
    assert saved_body["list_name"] == "Weekend"

    collections_resp = await client.get("/collections/", headers=headers)
    assert collections_resp.status_code == 200
    collections_body = collections_resp.json()
    assert collections_body["total"] == 1
    assert collections_body["items"][0]["name"] == "Weekend"

    async with AsyncSessionLocal() as session:
        coll_res = await session.execute(
            select(UserCollection).where(
                UserCollection.user_id == user_id,
                UserCollection.name == "Weekend",
            )
        )
        collection = coll_res.scalar_one()
        collection_id = collection.id
        members = await session.execute(
            select(func.count(UserCollectionPlace.id)).where(
                UserCollectionPlace.collection_id == collection_id
            )
        )
        assert members.scalar_one() == 1

    delete_resp = await client.delete(
        f"/places/saved/{place_id}", headers=headers)
    assert delete_resp.status_code == 204

    async with AsyncSessionLocal() as session:
        remaining = await session.execute(
            select(func.count(UserCollectionPlace.id))
            .where(UserCollectionPlace.collection_id == collection_id)
        )
        assert remaining.scalar_one() == 0
        saved_count = await session.execute(
            select(func.count(SavedPlace.id)).where(
                SavedPlace.user_id == user_id,
                SavedPlace.place_id == place_id,
            )
        )
        assert saved_count.scalar_one() == 0


@pytest.mark.asyncio
async def test_collection_add_creates_saved_place(client, auth_headers):
    headers, user_id = auth_headers
    place_id = await _create_place()

    create_resp = await client.post(
        "/collections/",
        json={"name": "Brunch Club", "description": None, "is_public": True},
        headers=headers,
    )
    assert create_resp.status_code == 200
    collection_id = create_resp.json()["id"]

    add_resp = await client.post(
        f"/collections/{collection_id}/places/{place_id}",
        headers=headers,
    )
    assert add_resp.status_code == 200
    add_body = add_resp.json()
    assert add_body["id"] is not None

    async with AsyncSessionLocal() as session:
        saved_res = await session.execute(
            select(SavedPlace).where(
                SavedPlace.user_id == user_id,
                SavedPlace.place_id == place_id,
            )
        )
        saved = saved_res.scalar_one_or_none()
        assert saved is not None
        assert saved.list_name == "Brunch Club"

        mapping_res = await session.execute(
            select(UserCollectionPlace).where(
                UserCollectionPlace.collection_id == collection_id,
                UserCollectionPlace.place_id == place_id,
            )
        )
        assert mapping_res.scalar_one_or_none() is not None

    remove_resp = await client.delete(
        f"/collections/{collection_id}/places/{place_id}",
        headers=headers,
    )
    assert remove_resp.status_code == 204

    async with AsyncSessionLocal() as session:
        saved_count = await session.execute(
            select(func.count(SavedPlace.id)).where(
                SavedPlace.user_id == user_id,
                SavedPlace.place_id == place_id,
            )
        )
        assert saved_count.scalar_one() == 0
