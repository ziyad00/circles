import pytest
import pytest_asyncio
import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.models import User, Friendship, CheckIn, Place


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


async def auth_token_email(client: httpx.AsyncClient, email: str) -> str:
    """Helper to get auth token for an email."""
    await client.post("/auth/request-otp", json={"email": email})
    
    # Get OTP from database (in dev mode)
    from app.models import OTPCode, User
    from app.database import get_db
    async for db in get_db():
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        result = await db.execute(
            select(OTPCode)
            .where(OTPCode.user_id == user.id)
            .order_by(OTPCode.created_at.desc())
        )
        otp = result.scalars().first()
        break
    
    response = await client.post("/auth/verify-otp", json={"email": email, "otp_code": otp.code})
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_complete_friends_flow(client: httpx.AsyncClient):
    """Test the complete friends flow including privacy enforcement."""
    # Create three users
    email1 = "friend1@test.com"
    email2 = "friend2@test.com"
    email3 = "stranger@test.com"
    
    token1 = await auth_token_email(client, email1)
    token2 = await auth_token_email(client, email2)
    token3 = await auth_token_email(client, email3)
    
    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}
    headers3 = {"Authorization": f"Bearer {token3}"}
    
    # 1. User1 sends friend request to User2
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": email2},
        headers=headers1
    )
    assert response.status_code == 200
    request_data = response.json()
    assert request_data["status"] == "pending"
    request_id = request_data["id"]
    
    # 2. User2 should see the pending request
    response = await client.get("/friends/requests", headers=headers2)
    assert response.status_code == 200
    requests_data = response.json()
    assert requests_data["total"] == 1
    assert requests_data["items"][0]["status"] == "pending"
    
    # 3. User1 should not see any incoming requests
    response = await client.get("/friends/requests", headers=headers1)
    assert response.status_code == 200
    requests_data = response.json()
    assert requests_data["total"] == 0
    
    # 4. Neither user should have friends yet
    for headers in [headers1, headers2]:
        response = await client.get("/friends", headers=headers)
        assert response.status_code == 200
        assert response.json()["total"] == 0
    
    # 5. User2 accepts the request
    response = await client.put(
        f"/friends/requests/{request_id}",
        json={"status": "accepted"},
        headers=headers2
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    
    # 6. Both users should now see each other as friends
    for headers, expected_email in [(headers1, email2), (headers2, email1)]:
        response = await client.get("/friends", headers=headers)
        assert response.status_code == 200
        friends_data = response.json()
        assert friends_data["total"] == 1
        assert friends_data["items"][0]["email"] == expected_email
    
    # 7. No pending requests should remain
    response = await client.get("/friends/requests", headers=headers2)
    assert response.status_code == 200
    assert response.json()["total"] == 0
    
    # 8. Test privacy enforcement with check-ins
    # Create a place
    place_data = {
        "name": "Friends Test Cafe",
        "address": "123 Privacy St",
        "city": "San Francisco"
    }
    response = await client.post("/places/", json=place_data)
    assert response.status_code == 200
    place_id = response.json()["id"]
    
    # User1 creates a check-in with "friends" visibility
    checkin_data = {
        "place_id": place_id,
        "note": "Friends only check-in",
        "visibility": "friends"
    }
    response = await client.post("/places/check-ins", json=checkin_data, headers=headers1)
    assert response.status_code == 200
    
    # User1 creates a private check-in
    checkin_data = {
        "place_id": place_id,
        "note": "Private check-in",
        "visibility": "private"
    }
    response = await client.post("/places/check-ins", json=checkin_data, headers=headers1)
    assert response.status_code == 200
    
    # User1 creates a public check-in
    checkin_data = {
        "place_id": place_id,
        "note": "Public check-in",
        "visibility": "public"
    }
    response = await client.post("/places/check-ins", json=checkin_data, headers=headers1)
    assert response.status_code == 200
    
    # 9. Test "Who's Here" visibility
    # User1 (owner) should see all 3 check-ins
    response = await client.get(f"/places/{place_id}/whos-here", headers=headers1)
    assert response.status_code == 200
    checkins = response.json()
    assert len(checkins) == 3
    notes = [c["note"] for c in checkins]
    assert "Friends only check-in" in notes
    assert "Private check-in" in notes
    assert "Public check-in" in notes
    
    # User2 (friend) should see friends + public check-ins (2 total)
    response = await client.get(f"/places/{place_id}/whos-here", headers=headers2)
    assert response.status_code == 200
    checkins = response.json()
    assert len(checkins) == 2
    notes = [c["note"] for c in checkins]
    assert "Friends only check-in" in notes
    assert "Public check-in" in notes
    assert "Private check-in" not in notes
    
    # User3 (stranger) should only see public check-in (1 total)
    response = await client.get(f"/places/{place_id}/whos-here", headers=headers3)
    assert response.status_code == 200
    checkins = response.json()
    assert len(checkins) == 1
    assert checkins[0]["note"] == "Public check-in"
    
    # 10. Test "Who's Here Count" visibility
    # Count should also respect privacy settings
    response = await client.get(f"/places/{place_id}/whos-here/count", headers=headers1)
    assert response.status_code == 200
    assert response.json()["count"] == 3
    
    response = await client.get(f"/places/{place_id}/whos-here/count", headers=headers2)
    assert response.status_code == 200
    assert response.json()["count"] == 2
    
    response = await client.get(f"/places/{place_id}/whos-here/count", headers=headers3)
    assert response.status_code == 200
    assert response.json()["count"] == 1


@pytest.mark.asyncio
async def test_friend_request_edge_cases(client: httpx.AsyncClient):
    """Test edge cases in friend request handling."""
    email1 = "edge1@test.com"
    email2 = "edge2@test.com"
    
    token1 = await auth_token_email(client, email1)
    token2 = await auth_token_email(client, email2)
    
    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    # 1. Cannot send friend request to yourself
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": email1},
        headers=headers1
    )
    assert response.status_code == 400
    assert "yourself" in response.json()["detail"]
    
    # 2. Send valid friend request
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": email2},
        headers=headers1
    )
    assert response.status_code == 200
    request_id = response.json()["id"]
    
    # 3. Cannot send duplicate friend request
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": email2},
        headers=headers1
    )
    assert response.status_code == 400
    assert "already sent" in response.json()["detail"]
    
    # 4. Addressee cannot send reverse request
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": email1},
        headers=headers2
    )
    assert response.status_code == 400
    assert "already received" in response.json()["detail"]
    
    # 5. Reject the request
    response = await client.put(
        f"/friends/requests/{request_id}",
        json={"status": "rejected"},
        headers=headers2
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    
    # 6. After rejection, can send a new request
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": email2},
        headers=headers1
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    new_request_id = response.json()["id"]
    
    # 7. Cancel the request
    response = await client.delete(f"/friends/requests/{new_request_id}", headers=headers1)
    assert response.status_code == 200
    assert "cancelled" in response.json()["message"]
    
    # 8. Request should be gone
    response = await client.get("/friends/requests", headers=headers2)
    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_remove_friend(client: httpx.AsyncClient):
    """Test removing a friend."""
    email1 = "remove1@test.com"
    email2 = "remove2@test.com"
    
    token1 = await auth_token_email(client, email1)
    token2 = await auth_token_email(client, email2)
    
    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    # 1. Send and accept friend request
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": email2},
        headers=headers1
    )
    assert response.status_code == 200
    request_id = response.json()["id"]
    
    response = await client.put(
        f"/friends/requests/{request_id}",
        json={"status": "accepted"},
        headers=headers2
    )
    assert response.status_code == 200
    
    # 2. Verify they are friends
    response = await client.get("/friends", headers=headers1)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    friend_id = response.json()["items"][0]["id"]
    
    # 3. Remove friend
    response = await client.delete(f"/friends/{friend_id}", headers=headers1)
    assert response.status_code == 200
    assert "removed" in response.json()["message"]
    
    # 4. Verify they are no longer friends
    for headers in [headers1, headers2]:
        response = await client.get("/friends", headers=headers)
        assert response.status_code == 200
        assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_nonexistent_user_request(client: httpx.AsyncClient):
    """Test sending friend request to nonexistent user."""
    email1 = "real@test.com"
    token1 = await auth_token_email(client, email1)
    headers1 = {"Authorization": f"Bearer {token1}"}
    
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": "nonexistent@test.com"},
        headers=headers1
    )
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]
