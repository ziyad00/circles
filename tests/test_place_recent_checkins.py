import asyncio
import random
import time

import pytest
import pytest_asyncio
import httpx

from app.main import app
from app.database import AsyncSessionLocal
from app.models import User
from app.services.jwt_service import JWTService


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def create_user_token() -> str:
    phone = "+1550" + f"{int(time.time()) % 10000:04d}{random.randint(1000, 9999)}"
    async with AsyncSessionLocal() as session:
        user = User(phone=phone, is_verified=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return JWTService.create_token(user.id)


@pytest.mark.asyncio
async def test_recent_checkins_count_and_price_tier(client: httpx.AsyncClient):
    # Create a place near downtown SF
    place_resp = await client.post(
        "/places/",
        json={
            "name": "Presence Cafe",
            "city": "San Francisco",
            "neighborhood": "SoMa",
            "categories": ["coffee", "cafe"],
            "latitude": 37.781,
            "longitude": -122.404,
            "price_tier": "$$",
        },
    )
    assert place_resp.status_code == 200
    place_id = place_resp.json()["id"]

    # Authenticate and create a check-in for the place
    token = await create_user_token()
    headers = {"Authorization": f"Bearer {token}"}
    checkin_resp = await client.post(
        "/places/check-ins",
        headers=headers,
        json={
            "place_id": place_id,
            "note": "Quick coffee",
            "latitude": 37.781,
            "longitude": -122.404,
        },
    )
    assert checkin_resp.status_code == 200, checkin_resp.json()

    # Nearby endpoint should include recent check-ins count within chat window
    nearby_resp = await client.get(
        "/places/nearby",
        params={
            "lat": 37.780,
            "lng": -122.405,
            "radius_m": 1000,
            "limit": 5,
            "offset": 0,
        },
    )
    assert nearby_resp.status_code == 200
    nearby_body = nearby_resp.json()
    assert any("recent_checkins_count" in item for item in nearby_body["items"])
    target_nearby = next(
        (item for item in nearby_body["items"] if item["id"] == place_id),
        None,
    )
    assert target_nearby is not None
    assert target_nearby["recent_checkins_count"] >= 1
    assert target_nearby["price_tier"] == "$$"

    # Trending endpoint should surface the same counter
    trending_resp = await client.get(
        "/places/trending",
        params={
            "lat": 37.780,
            "lng": -122.405,
            "limit": 5,
        },
    )
    assert trending_resp.status_code == 200
    trending_body = trending_resp.json()
    assert any("recent_checkins_count" in item for item in trending_body["items"])
    target_trending = next(
        (item for item in trending_body["items"] if item["id"] == place_id),
        None,
    )
    assert target_trending is not None
    assert target_trending["recent_checkins_count"] >= 1
    assert target_trending["price_tier"] == "$$"
