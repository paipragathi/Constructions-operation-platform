# ADR-003: SQLAlchemy 2.x Async with asyncpg

**Status:** Accepted  
**Date:** 2026-08-01  
**Deciders:** Engineering

---

## Context

The application runs on an async event loop (FastAPI / Starlette). Every
request handler is a coroutine. If the database driver blocks the event loop
— even for 5ms — it serialises all concurrent requests behind that one query.

We need a Python database access layer that:
1. Runs all I/O without blocking the event loop
2. Provides an ORM for complex domain models with relationships
3. Handles connection pooling, transactions, and migrations
4. Produces SQL that can be audited in logs and profiled in `pg_stat_statements`

---

## Decision

Use **SQLAlchemy 2.x** with the async extension (`sqlalchemy[asyncio]`) and
the **asyncpg** driver.

```python
engine = create_async_engine(
    settings.database_url_str,  # postgresql+asyncpg://...
    pool_size=10,
    pool_pre_ping=True,
    echo=settings.db_echo,
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)
```

---

## Rationale

### 1. asyncpg is the fastest Python PostgreSQL driver

asyncpg is a native async PostgreSQL driver built on Python's `asyncio`
protocol directly — it does not wrap a sync driver. Benchmarks consistently
show asyncpg outperforming psycopg2 and psycopg3 by 2–3× on throughput-heavy
workloads. For a multi-tenant SaaS with concurrent site engineers submitting
attendance and GRNs, latency at the DB layer compounds quickly.

### 2. SQLAlchemy 2.x async is production-grade

SQLAlchemy added true async support in 2.0 (released 2023). The async session
API (`AsyncSession`, `async_sessionmaker`) and the new 2.0 query style (`select()`,
`.execute()`) are fully supported — not a bolted-on wrapper. The ORM still
generates exactly the SQL you'd write by hand; nothing is hidden.

### 3. expire_on_commit=False is mandatory for async

In sync SQLAlchemy, accessing an attribute on an expired object after commit
triggers a lazy reload. In async context, that lazy reload would require an
await that the ORM cannot insert automatically, causing `MissingGreenlet` errors.
Setting `expire_on_commit=False` means objects retain their attribute values
after commit — correct and required behaviour for async.

### 4. Alembic handles migrations natively

SQLAlchemy's metadata system directly drives Alembic's `autogenerate`. We
define models in Python, run `alembic revision --autogenerate`, and get
migration scripts. The same `Base.metadata` used by the ORM is used by the
migration — they cannot drift from each other.

The async engine requires a small bridge in `alembic/env.py`:
```python
async with connectable.connect() as connection:
    await connection.run_sync(do_run_migrations)
```

### 5. The repository pattern isolates async complexity

All `await session.execute(select(...))` calls live inside repository classes.
Service layer and API handlers see only domain objects and simple method calls.
This isolates the async SQLAlchemy API surface to one layer and makes testing
straightforward: inject a session override, wrap in a transaction, roll back.

---

## Alternatives Considered

| Option | Why Not Chosen |
|---|---|
| **Tortoise ORM** | Django-inspired, async-native, but smaller community; Alembic incompatible (uses Aerich which is less mature); fewer escape hatches for raw SQL |
| **SQLModel** | Thin wrapper over SQLAlchemy + Pydantic; good DX but the abstraction occasionally leaks; we preferred direct SQLAlchemy control given the complexity of our domain |
| **Piccolo ORM** | Async-native with its own migration tool; very small ecosystem; insufficient community to de-risk a production bet |
| **psycopg3 (async)** | Excellent new driver; but would require writing raw SQL or a thin query builder — SQLAlchemy gives us ORM + Core + migration tooling in one package |
| **sync SQLAlchemy + run_in_executor** | Would allow sync SQLAlchemy but offloads every query to a thread pool; wastes threads, adds context-switching overhead, doesn't actually free the event loop from waiting |

---

## Consequences

### Positive
- Non-blocking database queries; event loop never stalls on I/O
- asyncpg connection pool keeps N connections warm; no per-request handshake
- `pool_pre_ping=True` detects stale connections before handing them to a handler
- Alembic migrations are a first-class citizen of the same codebase

### Negative
- SQLAlchemy async has sharper edges than sync: `lazy="noload"` is required
  on all relationships (lazy loading in async context raises an error);
  `.refresh()` requires an explicit `await`; `expire_on_commit=False` changes
  object lifecycle semantics
- Learning curve: developers familiar with sync SQLAlchemy need to unlearn
  several patterns before the async version feels natural
- `run_sync` bridge in Alembic is a non-obvious pattern — documented in
  `alembic/env.py` with a comment explaining why

---

## Review Trigger

Revisit if:
- psycopg3's async performance catches up with asyncpg and offers a
  cleaner integration story
- The SQLAlchemy async API introduces a breaking change that requires
  significant migration effort
