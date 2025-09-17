import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import AsyncSessionLocal
from app.models import User
from app.services.jwt_service import JWTService
from app.routers.dms_ws import update_user_availability_from_connection, manager


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers():
    async with AsyncSessionLocal() as session:
        user = User(
            phone="+1234567890",
            username="availability_user",
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = JWTService.create_token(user.id)
        yield {"Authorization": f"Bearer {token}"}, user.id


async def test_update_and_fetch_availability_status(client, auth_headers):
    headers, user_id = auth_headers

    try:
        # Default state: auto mode + offline
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            assert user.availability_status == "not_available"
            assert user.availability_mode == "auto"

        # Simulate WebSocket connection updating availability to online (auto mode)
        async with AsyncSessionLocal() as session:
            await update_user_availability_from_connection(session, user_id, True)

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            assert user.availability_status == "available"
            assert user.availability_mode == "auto"

        # User manually sets themselves offline
        response = await client.put(
            "/users/me",
            json={"availability_status": "not_available"},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["availability_status"] == "not_available"
        assert data["availability_mode"] == "manual"

        # Auto updates should not override manual mode
        async with AsyncSessionLocal() as session:
            await update_user_availability_from_connection(session, user_id, True)

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            assert user.availability_status == "not_available"
            assert user.availability_mode == "manual"

        profile_response = await client.get(f"/users/{user_id}", headers=headers)
        assert profile_response.status_code == 200
        profile_data = profile_response.json()
        assert profile_data["availability_status"] == "not_available"
        assert profile_data["availability_mode"] == "manual"

        # Switching back to available should place the user in auto mode but remain offline until active
        response = await client.put(
            "/users/me",
            json={"availability_status": "available"},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["availability_status"] == "not_available"
        assert data["availability_mode"] == "auto"

        # Simulate active connection again
        async with AsyncSessionLocal() as session:
            await update_user_availability_from_connection(session, user_id, True)

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            assert user.availability_status == "available"
            assert user.availability_mode == "auto"

        # Simulate disconnect to ensure status drops to offline
        async with AsyncSessionLocal() as session:
            await update_user_availability_from_connection(session, user_id, False)

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            assert user.availability_status == "not_available"
            assert user.availability_mode == "auto"
    finally:
        # Ensure connection manager state does not leak between tests
        manager.user_connections.clear()
        manager.active.clear()
