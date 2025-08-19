from app.models import Base
from app.config import settings
from sqlalchemy import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import pytest
import asyncio
import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# Override database URL for testing
@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set up test environment variables."""
    os.environ["APP_DATABASE_URL"] = "postgresql+asyncpg://postgres:password@127.0.0.1:5432/circles_test"
    os.environ["APP_DEBUG"] = "true"
    os.environ["APP_APP_NAME"] = "Circles Test"
    yield


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    # Parse the database URL and force asyncpg driver
    parsed_url = make_url(settings.database_url)
    database_url = URL.create(
        drivername="postgresql+asyncpg",
        username=parsed_url.username,
        password=parsed_url.password,
        host=parsed_url.host,
        port=parsed_url.port,
        database=parsed_url.database
    )

    engine = create_async_engine(
        database_url,
        echo=False,  # Disable SQL logging for tests
        future=True,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    """Create test database session."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        # Clean up after each test
        await session.rollback()


@pytest.fixture
def test_db_session(test_session):
    """Provide test database session for dependency injection."""
    return test_session
