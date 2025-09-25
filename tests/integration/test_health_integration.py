"""Integration tests for health endpoint."""

import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_integration():
    """Test health endpoint with full app integration."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "app" in data


@pytest.mark.asyncio
async def test_health_endpoint_headers():
    """Test health endpoint returns proper headers."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_health_endpoint_performance():
    """Test health endpoint responds quickly."""
    import time

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start_time = time.time()
        response = await client.get("/health")
        end_time = time.time()

        assert response.status_code == 200
        assert (end_time - start_time) < 1.0  # Should respond within 1 second
