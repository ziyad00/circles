from app.config import settings
from app.models import Base
from logging.config import fileConfig
from sqlalchemy import engine_from_config, make_url
from sqlalchemy import pool
from alembic import context
import os
import sys

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.
# Ensure Alembic always uses a synchronous driver


def _synchronous_url(async_url: str) -> str:
    url = make_url(async_url)
    driver = url.drivername

    if driver == "postgresql+asyncpg":
        url = url.set(drivername="postgresql+psycopg")
    elif driver in {"postgresql+psycopg_async", "postgresql+psycopg2"}:
        url = url.set(drivername="postgresql+psycopg")
    elif driver == "sqlite+aiosqlite":
        url = url.set(drivername="sqlite+pysqlite")
    elif "+" in driver:
        # Fallback: drop async suffix if present
        url = url.set(drivername=driver.split("+")[0])

    return str(url)


sync_database_url = _synchronous_url(settings.database_url)
config.set_main_option("sqlalchemy.url", sync_database_url)


def get_url():
    return sync_database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
