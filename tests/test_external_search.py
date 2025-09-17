import pytest
import pytest_asyncio
from sqlalchemy import select
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db, AsyncSessionLocal
from app.models import ExternalSearchSnapshot
from app.services.place_data_service_v2 import enhanced_place_data_service


@pytest_asyncio.fixture
async def client(test_session):
    async def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_external_search_stores_snapshot(monkeypatch, client):
    async def fake_search_live_overpass(*_, **__):
        return [
            {
                "name": "Cafe Blue",
                "latitude": 37.7805,
                "longitude": -122.4105,
                "categories": "amenity:cafe",
                "address": "123 Market St",
                "city": "San Francisco",
                "external_id": "osm_node_1",
                "data_source": "osm_overpass",
                "distance_m": 120.0,
            }
        ]

    monkeypatch.setattr(
        enhanced_place_data_service,
        "search_live_overpass",
        fake_search_live_overpass,
    )

    response = await client.get(
        "/places/external/search",
        params={"lat": 37.78, "lon": -122.41, "radius": 500, "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "osm_overpass"
    assert payload["count"] == 1
    assert payload["results"][0]["name"] == "Cafe Blue"
    assert payload["snapshot_id"] is not None

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ExternalSearchSnapshot))
        snapshot = result.scalars().first()
        assert snapshot is not None
        assert snapshot.result_count == 1
        assert snapshot.results[0]["name"] == "Cafe Blue"
