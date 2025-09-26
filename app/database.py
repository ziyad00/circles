from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import URL, make_url
from .config import settings
from .models import Base

# Create async engine with appropriate driver based on URL scheme
parsed_url = make_url(settings.database_url)
if parsed_url.drivername and parsed_url.drivername.startswith('sqlite'):
    # For SQLite, use aiosqlite driver
    database_url = URL.create(
        drivername="sqlite+aiosqlite",
        database=parsed_url.database
    )
else:
    # For PostgreSQL, use asyncpg driver
    database_url = URL.create(
        drivername="postgresql+asyncpg",
        username=parsed_url.username,
        password=parsed_url.password,
        host=parsed_url.host,
        port=parsed_url.port,
        database=parsed_url.database,
        query=parsed_url.query  # Preserve SSL and other query parameters
    )

engine = create_async_engine(
    database_url,
    echo=settings.debug,  # Only echo SQL in debug mode
    future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    """Dependency to get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables():
    """Create all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    """Drop all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
