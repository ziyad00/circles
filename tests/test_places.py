import asyncio
import pytest
import pytest_asyncio
import httpx
from app.main import app
from app.database import get_db
from app.services.jwt_service import JWTService
from app.services.place_data_service_v2 import enhanced_place_data_service


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
    # Use phone-only onboarding OTP
    import time
    import random
    phone = "+1550" + \
        f"{int(time.time()) % 10000:04d}{random.randint(1000, 9999)}"
    r = await client.post("/onboarding/request-otp", json={"phone": phone})
    otp = (r.json() or {}).get("otp", "")
    r = await client.post("/onboarding/verify-otp", json={"phone": phone, "otp_code": otp})
    return (r.json() or {}).get("access_token", "")


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
    r = await client.get("/places/trending")
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 10 and body["offset"] == 0 and body["total"] >= 1
    assert isinstance(body["items"], list) and len(body["items"]) >= 1

    # Test enhanced place endpoint (now the main place endpoint)
    r = await client.get(f"/places/{place_id}", headers=headers)
    assert r.status_code == 200
    enhanced_place = r.json()
    assert enhanced_place["id"] == place_id
    assert "stats" in enhanced_place
    assert "current_checkins" in enhanced_place
    assert "total_checkins" in enhanced_place
    assert "recent_reviews" in enhanced_place
    assert "photos_count" in enhanced_place
    assert "is_checked_in" in enhanced_place
    assert "is_saved" in enhanced_place
    # Should include our check-in
    assert enhanced_place["current_checkins"] >= 1
    assert enhanced_place["is_checked_in"] is True  # User should be checked in

    # Test place stats endpoint
    r = await client.get(f"/places/{place_id}/stats")
    assert r.status_code == 200
    stats = r.json()
    assert stats["place_id"] == place_id
    assert "average_rating" in stats
    assert "reviews_count" in stats
    assert "active_checkins" in stats
    assert stats["active_checkins"] >= 1

    # Test who's here endpoint
    r = await client.get(f"/places/{place_id}/whos-here", headers=headers)
    assert r.status_code == 200
    whos_here = r.json()
    assert whos_here["total"] >= 1
    assert len(whos_here["items"]) >= 1

    # Test who's here count endpoint
    r = await client.get(f"/places/{place_id}/whos-here-count", headers=headers)
    assert r.status_code == 200
    count = r.json()
    assert count["place_id"] == place_id
    assert count["count"] >= 1

    # Test place photos endpoint
    r = await client.get(f"/places/{place_id}/photos")
    assert r.status_code == 200
    photos = r.json()
    assert "items" in photos
    assert "total" in photos

    # Test place reviews endpoint
    r = await client.get(f"/places/{place_id}/reviews")
    assert r.status_code == 200
    reviews = r.json()
    assert "items" in reviews
    assert "total" in reviews


async def auth_token_email(client: httpx.AsyncClient, label: str) -> str:
    # Phone-based token helper; label used to vary number
    import time
    safe_digits = sum(ord(c) for c in (label or "a")) % 10000
    phone = "+1551" + f"{safe_digits:04d}{int(time.time()) % 10000:04d}"
    r = await client.post("/onboarding/request-otp", json={"phone": phone})
    otp = (r.json() or {}).get("otp", "")
    r = await client.post("/onboarding/verify-otp", json={"phone": phone, "otp_code": otp})
    return (r.json() or {}).get("access_token", "")


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

    # who's-here should only show public entries (now requires auth)
    r = await client.get(f"/places/{place_id}/whos-here", headers=headers1, params={"limit": 10, "offset": 0})
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

    # whos-here list (now requires auth)
    r = await client.get(f"/places/{place_id}/whos-here", headers=headers1)
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
async def test_nearby_places(client: httpx.AsyncClient, monkeypatch):
    async def fake_search_live_overpass(*_, **__):
        return [
            {
                "name": "OSM Pop Up",
                "latitude": 37.7810,
                "longitude": -122.4095,
                "categories": "amenity:cafe",
                "address": "456 Mission St",
                "city": "San Francisco",
                "external_id": "osm_node_test",
                "data_source": "osm_overpass",
                "distance_m": 75.0,
            }
        ]

    monkeypatch.setattr(
        enhanced_place_data_service,
        "search_live_overpass",
        fake_search_live_overpass,
    )
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
    assert body["external_count"] >= 1
    assert len(body["external_results"]) == body["external_count"]
    assert body["external_results"][0]["name"] == "OSM Pop Up"
    assert body["external_snapshot_id"] is not None


@pytest.mark.asyncio
async def test_delete_checkin_unauthorized(client: httpx.AsyncClient):
    # create a place
    r = await client.post(
        "/places/",
        json={
            "name": "Delete Unauthorized",
            "city": "SF",
            "categories": ["coffee"],
        },
    )
    assert r.status_code == 200
    place_id = r.json()["id"]

    # user A creates check-in
    token_a = await auth_token_email(client, "del_a@test.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    r = await client.post(
        "/places/check-ins",
        headers=headers_a,
        json={"place_id": place_id, "note": "mine"},
    )
    assert r.status_code == 200
    checkin_id = r.json()["id"]

    # user B attempts to delete A's check-in
    token_b = await auth_token_email(client, "del_b@test.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    r = await client.delete(f"/places/check-ins/{checkin_id}", headers=headers_b)
    assert r.status_code == 403
