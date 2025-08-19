import pytest
import pytest_asyncio
import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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


@pytest.mark.asyncio
async def test_friends_endpoints_exist(client):
    """Test that the friends endpoints are accessible."""
    # Test that the friends router is included
    response = await client.get("/docs")
    assert response.status_code == 200
    
    # The friends endpoints should be available in the OpenAPI docs
    # We can't easily test the actual endpoints without authentication,
    # but we can verify the router is loaded by checking the app structure
    assert hasattr(app, 'routes')
    
    # Check that friends routes are included
    friends_routes = [route for route in app.routes if hasattr(route, 'tags') and 'friends' in route.tags]
    assert len(friends_routes) > 0


@pytest.mark.asyncio
async def test_friends_flow(client):
    """Test the complete friends flow: request, accept, list."""
    # Create two users
    email1 = "friend1@test.com"
    email2 = "friend2@test.com"
    
    # Request OTP for user1
    response = await client.post("/auth/request-otp", json={"email": email1})
    assert response.status_code == 200
    
    # Request OTP for user2
    response = await client.post("/auth/request-otp", json={"email": email2})
    assert response.status_code == 200
    
    # Get OTP codes from database (in dev mode)
    from app.models import OTPCode, User
    from app.database import get_db
    
    async for db in get_db():
        # Get user1's OTP
        result = await db.execute(select(User).where(User.email == email1))
        user1 = result.scalar_one()
        result = await db.execute(select(OTPCode).where(OTPCode.user_id == user1.id))
        otp1 = result.scalar_one()
        
        # Get user2's OTP
        result = await db.execute(select(User).where(User.email == email2))
        user2 = result.scalar_one()
        result = await db.execute(select(OTPCode).where(OTPCode.user_id == user2.id))
        otp2 = result.scalar_one()
        break
    
    # Verify OTPs and get tokens
    response = await client.post("/auth/verify-otp", json={"email": email1, "otp_code": otp1.code})
    assert response.status_code == 200
    token1 = response.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}
    
    response = await client.post("/auth/verify-otp", json={"email": email2, "otp_code": otp2.code})
    assert response.status_code == 200
    token2 = response.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    # User1 sends friend request to User2
    response = await client.post(
        "/friends/requests",
        json={"addressee_email": email2},
        headers=headers1
    )
    assert response.status_code == 200
    request_data = response.json()
    assert request_data["status"] == "pending"
    
    # User2 should see the pending request
    response = await client.get("/friends/requests", headers=headers2)
    assert response.status_code == 200
    requests_data = response.json()
    assert requests_data["total"] == 1
    assert requests_data["items"][0]["status"] == "pending"
    
    # User2 accepts the request
    request_id = requests_data["items"][0]["id"]
    response = await client.put(
        f"/friends/requests/{request_id}",
        json={"status": "accepted"},
        headers=headers2
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    
    # Both users should now see each other as friends
    response = await client.get("/friends", headers=headers1)
    assert response.status_code == 200
    friends_data = response.json()
    assert friends_data["total"] == 1
    assert friends_data["items"][0]["email"] == email2
    
    response = await client.get("/friends", headers=headers2)
    assert response.status_code == 200
    friends_data = response.json()
    assert friends_data["total"] == 1
    assert friends_data["items"][0]["email"] == email1
