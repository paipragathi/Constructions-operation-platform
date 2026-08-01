"""
Alembic environment configuration for async SQLAlchemy.

Key differences from the default env.py:
  1. Uses asyncpg (async driver), so migrations run via run_sync()
  2. Database URL is read from Settings (env var), not alembic.ini
  3. target_metadata is set to Base.metadata so autogenerate works
  4. compare_type=True detects column type changes in autogenerate
  5. NullPool: migrations should not use a connection pool

Alembic cannot use async natively — it runs synchronous migrations
wrapped in asyncio.run() via the async engine's sync interface.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Load Alembic config (alembic.ini)
alembic_config = context.config

# Set up Python logging from alembic.ini [loggers] section
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# Import all models so Alembic can see the full schema for autogenerate.
# This is why app/models/__init__.py must import every model.
from app.models import Base  # noqa: E402
from app.core.config import settings  # noqa: E402

# The metadata Alembic compares against the live DB schema
target_metadata = Base.metadata

# Sync database URL — convert asyncpg to psycopg2-compatible for Alembic
# asyncpg is only for runtime; Alembic needs a sync dialect
def get_sync_url() -> str:
    """
    Convert async DB URL to sync for Alembic.
    postgresql+asyncpg://... → postgresql+psycopg2://...

    Alembic runs migrations synchronously via run_sync(), not natively async.
    """
    url = settings.database_url_str
    return url.replace("postgresql+asyncpg://", "postgresql://")


def run_migrations_offline() -> None:
    """
    Run migrations without a live database connection (generates SQL only).
    Useful for generating migration SQL to review before applying.
    """
    context.configure(
        url=get_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,          # detect column type changes
        compare_server_default=True, # detect server_default changes
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations using an async engine with NullPool.

    NullPool: each migration operation uses a fresh connection.
    No connection pool for migrations — they run once and exit.
    """
    connectable = create_async_engine(
        settings.database_url_str,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # run_sync bridges the async connection to Alembic's sync interface
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
