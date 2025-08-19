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


@pytest.mark.asyncio
async def test_otp_throttle_per_minute(client: httpx.AsyncClient):
    email = "throttle@test.com"
    # Allow up to 5 per minute by default; the 6th should be 429
    for i in range(5):
        r = await client.post("/auth/request-otp", json={"email": email})
        assert r.status_code == 200, f"unexpected status at iter {i}: {r.status_code}"
    # 6th request should be throttled
    r = await client.post("/auth/request-otp", json={"email": email})
    assert r.status_code == 429
