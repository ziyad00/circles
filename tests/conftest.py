import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text

# Ensure pytest-asyncio plugin is active for async tests
pytest_plugins = ("pytest_asyncio",)

# Run tests inside the asyncio event loop by default
pytestmark = pytest.mark.asyncio
# Ensure project root on path before importing app modules
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Configure the app to use a local SQLite database during tests
_test_db_path = project_root / "test.db"
os.environ["APP_DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db_path.as_posix()}"
os.environ["APP_DEBUG"] = "false"

# Start each test session from a clean database file
if _test_db_path.exists():
    _test_db_path.unlink()


async def _clear_database(session) -> None:
    """Remove all data from the database between tests."""
    from app.models import Base

    await session.execute(text("PRAGMA foreign_keys=OFF"))
    for table in reversed(Base.metadata.sorted_tables):
        await session.execute(table.delete())
    await session.commit()
    await session.execute(text("PRAGMA foreign_keys=ON"))


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables for the duration of the test session."""
    from app.database import create_tables, drop_tables

    await create_tables()
    yield
    await drop_tables()
    if _test_db_path.exists():
        _test_db_path.unlink()


@pytest_asyncio.fixture
async def test_session(setup_database):
    """Provide an async database session to tests that need direct access."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        yield session
        await _clear_database(session)


@pytest_asyncio.fixture(autouse=True)
async def clean_database_after_test(setup_database):
    """Clean up any data created via API calls after each test."""
    yield
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await _clear_database(session)
