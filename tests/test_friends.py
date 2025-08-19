import pytest
import pytest_asyncio
import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.models import User, Friendship, CheckIn, Place
from app.schemas import VisibilityEnum


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


@pytest_asyncio.fixture
async def db():
    from app.database import get_db
    async for session in get_db():
        yield session


@pytest_asyncio.fixture
async def user1_headers(client):
    # Create user1
    email1 = "user1@test.com"
    await client.post("/auth/request-otp", json={"email": email1})

    # Get OTP from logs (in dev mode)
    from app.models import OTPCode
    from app.database import get_db
    async for db in get_db():
        otp = await db.execute(select(OTPCode).where(OTPCode.user_id == 1))
        otp_code = otp.scalar_one().code
        break

    # Verify OTP
    response = await client.post("/auth/verify-otp", json={"email": email1, "otp_code": otp_code})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user2_headers(client):
    # Create user2
    email2 = "user2@test.com"
    await client.post("/auth/request-otp", json={"email": email2})

    # Get OTP from logs (in dev mode)
    from app.models import OTPCode
    from app.database import get_db
    async for db in get_db():
        otp = await db.execute(select(OTPCode).where(OTPCode.user_id == 2))
        otp_code = otp.scalar_one().code
        break

    # Verify OTP
    response = await client.post("/auth/verify-otp", json={"email": email2, "otp_code": otp_code})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user3_headers(client):
    # Create user3
    email3 = "user3@test.com"
    await client.post("/auth/request-otp", json={"email": email3})

    # Get OTP from logs (in dev mode)
    from app.models import OTPCode
    from app.database import get_db
    async for db in get_db():
        otp = await db.execute(select(OTPCode).where(OTPCode.user_id == 3))
        otp_code = otp.scalar_one().code
        break

    # Verify OTP
    response = await client.post("/auth/verify-otp", json={"email": email3, "otp_code": otp_code})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_send_friend_request(client, user1_headers, user2_headers):
    """Test sending a friend request."""
    # User1 sends friend request to User2
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": "user2@test.com"},
        headers=user1_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["requester_id"] == 1
    assert data["addressee_id"] == 2


@pytest.mark.asyncio
async def test_duplicate_friend_request(client, user1_headers):
    """Test that duplicate friend requests are handled properly."""
    # Try to send another request to the same user
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": "user2@test.com"},
        headers=user1_headers
    )
    assert response.status_code == 400
    assert "already sent" in response.json()["detail"]


@pytest.mark.asyncio
async def test_self_friend_request(client, user1_headers):
    """Test that users cannot send friend requests to themselves."""
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": "user1@test.com"},
        headers=user1_headers
    )
    assert response.status_code == 400
    assert "yourself" in response.json()["detail"]


@pytest.mark.asyncio
async def test_accept_friend_request(client, user2_headers):
    """Test accepting a friend request."""
    # User2 accepts the friend request from User1
    response = await client.put(
        "/friends/requests/1",
        json={"status": "accepted"},
        headers=user2_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"


@pytest.mark.asyncio
async def test_list_friends(client, user1_headers, user2_headers):
    """Test listing friends after accepting a request."""
    # User1 should see User2 as a friend
    response = await client.get("/friends", headers=user1_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["email"] == "user2@test.com"

    # User2 should see User1 as a friend
    response = await client.get("/friends", headers=user2_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["email"] == "user1@test.com"


@pytest.mark.asyncio
async def test_list_friend_requests(client, user3_headers):
    """Test listing pending friend requests."""
    # User1 sends request to User3
    from app.models import User, Friendship
    from app.database import get_db
    async for db in get_db():
        user1 = await db.execute(select(User).where(User.email == "user1@test.com"))
        user1 = user1.scalar_one()
        user3 = await db.execute(select(User).where(User.email == "user3@test.com"))
        user3 = user3.scalar_one()

        friendship = Friendship(
            requester_id=user1.id,
            addressee_id=user3.id,
            status="pending"
        )
        db.add(friendship)
        await db.commit()
        break

    # User3 should see the pending request
    response = await client.get("/friends/requests", headers=user3_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_visibility_enforcement(client, user1_headers, user2_headers, user3_headers):
    """Test that check-in visibility is properly enforced based on friendship status."""
    # Create a place
    place_data = {
        "name": "Test Place",
        "address": "123 Test St",
        "city": "Test City"
    }
    response = await client.post("/places/", json=place_data, headers=user1_headers)
    assert response.status_code == 200
    place_id = response.json()["id"]

    # User1 creates a check-in with "friends" visibility
    from datetime import datetime, timezone, timedelta
    checkin_data = {
        "place_id": place_id,
        "note": "Friends only check-in",
        "visibility": "friends"
    }
    response = await client.post(f"/places/{place_id}/check-in", json=checkin_data, headers=user1_headers)
    assert response.status_code == 200

    # User2 (friend) should see the check-in
    response = await client.get(f"/places/{place_id}/whos-here", headers=user2_headers)
    assert response.status_code == 200
    checkins = response.json()
    assert len(checkins) == 1
    assert checkins[0]["note"] == "Friends only check-in"

    # User3 (not friend) should not see the check-in
    response = await client.get(f"/places/{place_id}/whos-here", headers=user3_headers)
    assert response.status_code == 200
    checkins = response.json()
    assert len(checkins) == 0

    # User1 creates a private check-in
    checkin_data = {
        "place_id": place_id,
        "note": "Private check-in",
        "visibility": "private"
    }
    response = await client.post(f"/places/{place_id}/check-in", json=checkin_data, headers=user1_headers)
    assert response.status_code == 200

    # Only User1 should see the private check-in
    response = await client.get(f"/places/{place_id}/whos-here", headers=user1_headers)
    assert response.status_code == 200
    checkins = response.json()
    assert len(checkins) == 2  # Both check-ins visible to owner

    # User2 should only see the friends check-in
    response = await client.get(f"/places/{place_id}/whos-here", headers=user2_headers)
    assert response.status_code == 200
    checkins = response.json()
    assert len(checkins) == 1
    assert checkins[0]["note"] == "Friends only check-in"


@pytest.mark.asyncio
async def test_remove_friend(client, user1_headers, user2_headers):
    """Test removing a friend."""
    # User1 removes User2 as a friend
    response = await client.delete("/friends/2", headers=user1_headers)
    assert response.status_code == 200
    assert "removed" in response.json()["message"]

    # Verify they are no longer friends
    response = await client.get("/friends", headers=user1_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0

    response = await client.get("/friends", headers=user2_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_cancel_friend_request(client, user1_headers):
    """Test canceling a sent friend request."""
    # User1 sends a new request to User3
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": "user3@test.com"},
        headers=user1_headers
    )
    assert response.status_code == 200
    request_id = response.json()["id"]

    # User1 cancels the request
    response = await client.delete(f"/friends/requests/{request_id}", headers=user1_headers)
    assert response.status_code == 200
    assert "cancelled" in response.json()["message"]

    # Verify the request is gone
    response = await client.get("/friends/requests", headers=user1_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
