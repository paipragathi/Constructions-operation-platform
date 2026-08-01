"""
Async database engine, session factory, and FastAPI dependency.

Architecture decisions:
  - SQLAlchemy 2.x async with asyncpg driver
  - One engine per application (singleton, created at startup)
  - One session per HTTP request (created by get_db dependency, closed after response)
  - expire_on_commit=False: required for async — lazy loading is not possible
    in async context, so attributes must remain accessible after commit

Connection pool is configured via Settings. Tuning guidance:
  pool_size:    number of persistent connections. Start at 10.
  max_overflow: additional connections allowed under peak load.
  pool_recycle: replace connections older than N seconds (prevents stale
                connections after network interruptions or DB restarts).
  pool_pre_ping: test connection before use — handles DB restart gracefully.
"""

from collections.abc import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ── Engine ─────────────────────────────────────────────────────────────────────
# Created once at module load. In tests, a separate engine is created pointing
# at the test database (see tests/conftest.py).
engine: AsyncEngine = create_async_engine(
    settings.database_url_str,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,      # test connection before using from pool
    echo=settings.db_echo,   # log SQL statements (development only)
)

# ── Session factory ────────────────────────────────────────────────────────────
# async_sessionmaker returns a callable that creates AsyncSession instances.
# expire_on_commit=False: after session.commit(), ORM objects retain their
# attribute values instead of being expired. Required for async because
# lazy-loading would need an implicit await, which SQLAlchemy async prohibits.
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,   # we control when flushes happen — no surprises
    autocommit=False,  # explicit transaction management only
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides one AsyncSession per request.

    The session is committed on success and rolled back on any exception.
    The connection is returned to the pool after the response is sent.

    Usage in a router:
        @router.get("/workers/")
        async def list_workers(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """
    Verify the database is reachable. Used by the health check endpoint.
    Returns True if healthy, False if unreachable.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("database.health_check.failed", error=str(e))
        return False
