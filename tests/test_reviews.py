import asyncio
import pytest
import pytest_asyncio
import httpx
from app.main import app


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


async def auth_token(client: httpx.AsyncClient, email: str = "reviews@test.com") -> str:
    r = await client.post("/auth/request-otp", json={"email": email})
    otp = r.json()["message"].split(":")[-1].strip()
    r = await client.post("/auth/verify-otp", json={"email": email, "otp_code": otp})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_my_checkins_and_reviews(client: httpx.AsyncClient):
    # create a place
    r = await client.post(
        "/places/",
        json={
            "name": "Review Spot",
            "city": "San Francisco",
            "neighborhood": "SoMa",
            "categories": ["coffee"],
            "rating": 4.0,
        },
    )
    assert r.status_code == 200
    place_id = r.json()["id"]

    # auth
    token = await auth_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # check-in once
    r = await client.post(
        "/places/check-ins",
        headers=headers,
        json={"place_id": place_id, "note": "first"},
    )
    assert r.status_code == 200

    # my check-ins list
    r = await client.get("/places/me/check-ins", headers=headers, params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 10 and body["offset"] == 0 and body["total"] >= 1
    assert isinstance(body["items"], list) and len(body["items"]) >= 1


@pytest.mark.asyncio
async def test_review_upsert_and_stats(client: httpx.AsyncClient):
    # create a place without initial rating to rely on computed average
    r = await client.post(
        "/places/",
        json={
            "name": "Stats Spot",
            "city": "San Francisco",
            "neighborhood": "SoMa",
            "categories": ["coffee"],
        },
    )
    assert r.status_code == 200
    place_id = r.json()["id"]

    # user1 auth
    token1 = await auth_token(client)
    headers1 = {"Authorization": f"Bearer {token1}"}

    # create review 4.0
    r = await client.post(
        f"/places/{place_id}/reviews",
        headers=headers1,
        json={"rating": 4.0, "text": "ok"},
    )
    assert r.status_code == 200

    # stats should reflect average 4.0, count 1
    r = await client.get(f"/places/{place_id}/stats")
    assert r.status_code == 200
    stats = r.json()
    assert stats["average_rating"] == 4.0 and stats["reviews_count"] == 1

    # upsert review to 5.0
    r = await client.post(
        f"/places/{place_id}/reviews",
        headers=headers1,
        json={"rating": 5.0, "text": "great"},
    )
    assert r.status_code == 200
    r = await client.get(f"/places/{place_id}/stats")
    stats = r.json()
    assert stats["average_rating"] == 5.0 and stats["reviews_count"] == 1

    # user2 leaves a 3.0 review, average should be 4.0
    token2 = await auth_token(client, email="stats2@test.com")
    headers2 = {"Authorization": f"Bearer {token2}"}
    r = await client.post(
        f"/places/{place_id}/reviews",
        headers=headers2,
        json={"rating": 3.0, "text": "meh"},
    )
    assert r.status_code == 200
    r = await client.get(f"/places/{place_id}/stats")
    stats = r.json()
    assert stats["average_rating"] == 4.0 and stats["reviews_count"] == 2

    # user1 deletes review; average becomes 3.0, count 1
    r = await client.delete(f"/places/{place_id}/reviews/me", headers=headers1)
    assert r.status_code == 204
    r = await client.get(f"/places/{place_id}/stats")
    stats = r.json()
    assert stats["average_rating"] == 3.0 and stats["reviews_count"] == 1

    # user2 deletes review; no reviews remain
    r = await client.delete(f"/places/{place_id}/reviews/me", headers=headers2)
    assert r.status_code == 204
    r = await client.get(f"/places/{place_id}/stats")
    stats = r.json()
    assert stats["average_rating"] is None and stats["reviews_count"] == 0

    # create a review (again) to ensure list endpoint works
    r = await client.post(
        f"/places/{place_id}/reviews",
        headers=headers2,
        json={"rating": 4.5, "text": "Great place"},
    )
    assert r.status_code == 200
    review = r.json()
    assert review["rating"] == 4.5 and review["place_id"] == place_id

    # list reviews
    r = await client.get(
        f"/places/{place_id}/reviews",
        params={"limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 10 and body["offset"] == 0 and body["total"] >= 1
    assert isinstance(body["items"], list) and len(body["items"]) >= 1
