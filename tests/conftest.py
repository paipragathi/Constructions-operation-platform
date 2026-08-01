"""
Test fixtures.

Strategy:
  - Integration tests: spin up a real PostgreSQL via testcontainers,
    apply migrations, then use a per-test transaction that is rolled back.
  - Unit tests: mock the service layer; no DB needed.

Session-scoped fixtures (container, engine) are created once per test session.
Function-scoped fixtures (db, client) get a fresh, isolated transaction per test.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings
from app.main import create_app
from app.models.base import Base


# ── Session-scoped: shared across all tests ───────────────────────────────────

@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Start a real PostgreSQL container for the test session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def test_db_url(postgres_container: PostgresContainer) -> str:
    """Return the asyncpg URL for the test database."""
    sync_url = postgres_container.get_connection_url()
    return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default asyncio event loop policy."""
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_db_url: str):
    """Create all tables once per session, drop them after."""
    from sqlalchemy.pool import NullPool
    engine = create_async_engine(test_db_url, poolclass=NullPool, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Function-scoped: isolated transaction per test ────────────────────────────

@pytest_asyncio.fixture
async def db_connection(test_engine) -> AsyncGenerator[AsyncConnection, None]:
    """
    Provides a connection with a savepoint per test.
    The outer transaction is rolled back after each test so tests never leak data.
    """
    async with test_engine.connect() as conn:
        await conn.begin()
        yield conn
        await conn.rollback()


@pytest_asyncio.fixture
async def db(db_connection: AsyncConnection) -> AsyncGenerator[AsyncSession, None]:
    """
    AsyncSession bound to the per-test transaction.
    expire_on_commit=False is required for async SQLAlchemy.
    """
    session_factory = async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
        join_transaction_mode="create_savepoint",
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTPX async client wired to the FastAPI app, with the DB session
    overridden to use our per-test transaction.
    """
    from app.core.database import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db  # type: ignore[assignment]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Helper factories ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def org(db: AsyncSession) -> Any:
    """Insert a test organization and return it."""
    from app.models.organization import Organization

    organization = Organization(
        name="Test Construction Co",
        slug="test-construction-co",
        gstin=None,
        city="Hyderabad",
        state="Telangana",
    )
    db.add(organization)
    await db.flush()
    await db.refresh(organization)
    return organization


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession, org: Any) -> Any:
    """Insert an admin user and return it."""
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    user = User(
        organization_id=org.id,
        email="admin@test.com",
        full_name="Test Admin",
        password_hash=hash_password("Test1234!"),
        role=UserRole.ADMIN,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user
