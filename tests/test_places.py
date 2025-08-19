import asyncio
import pytest
import pytest_asyncio
import httpx
from app.main import app
from app.database import get_db
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


async def auth_token(client: httpx.AsyncClient) -> str:
    r = await client.post("/auth/request-otp", json={"email": "places@test.com"})
    otp = r.json()["message"].split(":")[-1].strip()
    r = await client.post("/auth/verify-otp", json={"email": "places@test.com", "otp_code": otp})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_places_flow(client: httpx.AsyncClient):
    # create places
    r = await client.post(
        "/places/",
        json={
            "name": "Demo Coffee",
            "city": "San Francisco",
            "neighborhood": "SoMa",
            "categories": ["coffee", "cafe"],
            "rating": 4.2,
        },
    )
    assert r.status_code == 200
    place_id = r.json()["id"]

    r2 = await client.post(
        "/places/",
        json={
            "name": "Demo Bakery",
            "city": "San Francisco",
            "neighborhood": "Mission",
            "categories": "bakery,cafe",
            "rating": 4.7,
        },
    )
    assert r2.status_code == 200

    # GET /places/{id}
    r = await client.get(f"/places/{place_id}")
    assert r.status_code == 200
    assert r.json()["id"] == place_id

    # search pagination
    r = await client.get("/places/search", params={"city": "San Francisco", "limit": 1, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 1 and body["offset"] == 0 and body["total"] >= 2
    assert isinstance(body["items"], list) and len(body["items"]) == 1

    r = await client.get("/places/search", params={"city": "San Francisco", "limit": 1, "offset": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 1 and body["offset"] == 1 and body["total"] >= 2
    assert isinstance(body["items"], list) and len(body["items"]) == 1

    # auth token
    token = await auth_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # check-in
    r = await client.post("/places/check-ins", headers=headers, json={"place_id": place_id, "note": "Hi"})
    assert r.status_code == 200

    # rate limit second check-in within 5 minutes
    r = await client.post("/places/check-ins", headers=headers, json={"place_id": place_id, "note": "Again"})
    assert r.status_code == 429

    # trending should include at least one
    r = await client.get("/places/trending", params={"city": "San Francisco", "hours": 24, "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 10 and body["offset"] == 0 and body["total"] >= 1
    assert isinstance(body["items"], list) and len(body["items"]) >= 1


async def auth_token_email(client: httpx.AsyncClient, email: str) -> str:
    r = await client.post("/auth/request-otp", json={"email": email})
    otp = r.json()["message"].split(":")[-1].strip()
    r = await client.post("/auth/verify-otp", json={"email": email, "otp_code": otp})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_whos_here_visibility_and_unsave_flow(client: httpx.AsyncClient):
    # create a place
    r = await client.post(
        "/places/",
        json={
            "name": "Visibility Test Cafe",
            "city": "San Francisco",
            "neighborhood": "SoMa",
            "categories": ["coffee"],
            "rating": 4.0,
        },
    )
    assert r.status_code == 200
    place_id = r.json()["id"]

    # two users
    token1 = await auth_token_email(client, "vis1@test.com")
    token2 = await auth_token_email(client, "vis2@test.com")
    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}

    # public check-in by user1
    r = await client.post(
        "/places/check-ins",
        headers=headers1,
        json={"place_id": place_id, "note": "public", "visibility": "public"},
    )
    assert r.status_code == 200

    # private check-in by user2 (should not appear in who's-here)
    r = await client.post(
        "/places/check-ins",
        headers=headers2,
        json={"place_id": place_id, "note": "private", "visibility": "private"},
    )
    assert r.status_code == 200

    # who's-here should only show public entries
    r = await client.get(f"/places/{place_id}/whos-here", params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    whos_here = r.json()
    assert isinstance(whos_here, list) and len(whos_here) >= 1
    assert all(item["visibility"] == "public" for item in whos_here)

    # save place, prevent duplicate, then unsave
    r = await client.post("/places/saved", headers=headers1, json={"place_id": place_id, "list_name": "Fav"})
    assert r.status_code == 200
    r = await client.get("/places/saved/me", headers=headers1, params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    first_total = r.json()["total"]
    assert first_total >= 1

    # attempt duplicate save
    r = await client.post("/places/saved", headers=headers1, json={"place_id": place_id, "list_name": "Fav"})
    assert r.status_code == 200
    r = await client.get("/places/saved/me", headers=headers1, params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    after_dup_total = r.json()["total"]
    assert after_dup_total == first_total

    # unsave
    r = await client.delete(f"/places/saved/{place_id}", headers=headers1)
    assert r.status_code == 204
    r = await client.get("/places/saved/me", headers=headers1, params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    after_unsave_total = r.json()["total"]
    assert after_unsave_total == max(0, first_total - 1)

    # whos-here list
    r = await client.get(f"/places/{place_id}/whos-here")
    assert r.status_code == 200
    assert len(r.json()) >= 1

    # save and list saved (paginated)
    r = await client.post("/places/saved", headers=headers1, json={"place_id": place_id, "list_name": "Fav"})
    assert r.status_code == 200
    r = await client.get("/places/saved/me", headers=headers1, params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 10 and body["offset"] == 0 and body["total"] >= 1
    assert isinstance(body["items"], list) and len(body["items"]) >= 1


@pytest.mark.asyncio
async def test_whos_here_count_and_delete_checkin(client: httpx.AsyncClient):
    # create a place
    r = await client.post(
        "/places/",
        json={
            "name": "Count Cafe",
            "city": "San Francisco",
            "neighborhood": "SoMa",
            "categories": ["coffee"],
        },
    )
    assert r.status_code == 200
    place_id = r.json()["id"]

    # two users
    token1 = await auth_token_email(client, "count1@test.com")
    token2 = await auth_token_email(client, "count2@test.com")
    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}

    # public and private check-ins
    r = await client.post(
        "/places/check-ins",
        headers=headers1,
        json={"place_id": place_id, "note": "public", "visibility": "public"},
    )
    assert r.status_code == 200
    public_checkin_id = r.json()["id"]

    r = await client.post(
        "/places/check-ins",
        headers=headers2,
        json={"place_id": place_id, "note": "private", "visibility": "private"},
    )
    assert r.status_code == 200

    # count should be 1 (only public non-expired)
    r = await client.get(f"/places/{place_id}/whos-here/count")
    assert r.status_code == 200 and r.json()["count"] == 1

    # delete public check-in and verify count becomes 0
    r = await client.delete(f"/places/check-ins/{public_checkin_id}", headers=headers1)
    assert r.status_code == 204
    r = await client.get(f"/places/{place_id}/whos-here/count")
    assert r.status_code == 200 and r.json()["count"] == 0


@pytest.mark.asyncio
async def test_nearby_places(client: httpx.AsyncClient):
    # near center (should come first)
    r = await client.post(
        "/places/",
        json={
            "name": "Near Spot",
            "city": "San Francisco",
            "neighborhood": "SoMa",
            "categories": ["coffee"],
            "latitude": 37.7805,
            "longitude": -122.4105,
        },
    )
    assert r.status_code == 200
    near_id = r.json()["id"]

    # farther spot
    r = await client.post(
        "/places/",
        json={
            "name": "Far Spot",
            "city": "San Francisco",
            "neighborhood": "Mission",
            "categories": ["cafe"],
            "latitude": 37.8000,
            "longitude": -122.5000,
        },
    )
    assert r.status_code == 200

    # nearby query around SoMa
    r = await client.get(
        "/places/nearby",
        params={"lat": 37.7800, "lng": -122.4100,
                "radius_m": 5000, "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert isinstance(body["items"], list) and len(body["items"]) >= 1
    # near spot should be first result
    assert body["items"][0]["id"] == near_id
