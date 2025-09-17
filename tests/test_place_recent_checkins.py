import asyncio
import random
import time
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import httpx

from app.main import app
from app.database import AsyncSessionLocal
from app.models import User, CheckIn, DMMessage
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


@pytest.mark.asyncio
async def test_recent_checkins_count_and_price_tier(client: httpx.AsyncClient):
    from app.config import settings as app_settings

    original_override = app_settings.fsq_trending_override
    original_enabled = app_settings.fsq_trending_enabled
    app_settings.fsq_trending_override = False
    app_settings.fsq_trending_enabled = False

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

    # Seed two verified users and recent check-ins directly in the database
    phone_a = "+1550" + f"{int(time.time()) % 10000:04d}{random.randint(1000, 9999)}"
    phone_b = "+1550" + f"{int(time.time()) % 10000:04d}{random.randint(1000, 9999)}"
    async with AsyncSessionLocal() as session:
        user_a = User(phone=phone_a, is_verified=True)
        user_b = User(phone=phone_b, is_verified=True)
        session.add_all([user_a, user_b])
        await session.flush()

        now = datetime.now(timezone.utc)
        checkins = [
            CheckIn(
                user_id=user_a.id,
                place_id=place_id,
                note="Quick coffee",
                visibility="public",
                created_at=now,
                expires_at=now + timedelta(hours=2),
            ),
            CheckIn(
                user_id=user_b.id,
                place_id=place_id,
                note="I'll be there",
                visibility="public",
                created_at=now,
                expires_at=now + timedelta(hours=2),
            ),
        ]
        session.add_all(checkins)
        await session.commit()
        user_a_id, user_b_id = user_a.id, user_b.id

    headers = {"Authorization": f"Bearer {JWTService.create_token(user_a_id)}"}

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

    try:
        # Trending endpoint should surface the same counter
        trending_resp = await client.get(
            "/places/trending/global",
            params={
                "limit": 5,
            },
        )
        assert trending_resp.status_code == 200
        trending_body = trending_resp.json()
        assert trending_body["items"], trending_body
        assert any("recent_checkins_count" in item for item in trending_body["items"])
        target_trending = next(
            (item for item in trending_body["items"] if item["id"] == place_id),
            None,
        )
        assert target_trending is not None
        assert target_trending["recent_checkins_count"] >= 1
        assert target_trending["price_tier"] == "$$"

        private_resp = await client.post(
            f"/places/{place_id}/chat/private-reply",
            headers=headers,
            json={
                "target_user_id": user_b_id,
                "text": "See you there!",
                "context_text": "Meet downstairs",
            },
        )
        assert private_resp.status_code == 200
        private_data = private_resp.json()
        assert private_data["thread_id"] > 0
        assert "Private reply from place chat" in private_data["text"]
        assert "See you there!" in private_data["text"]

        async with AsyncSessionLocal() as session:
            dm_msg = await session.get(DMMessage, private_data["id"])
            assert dm_msg is not None
            assert dm_msg.thread_id == private_data["thread_id"]
    finally:
        # Restore original Foursquare settings
        app_settings.fsq_trending_override = original_override
        app_settings.fsq_trending_enabled = original_enabled
