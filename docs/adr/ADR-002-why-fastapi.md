# ADR-002: FastAPI as the Web Framework

**Status:** Accepted  
**Date:** 2026-08-01  
**Deciders:** Engineering

---

## Context

We are building a REST API backend for a construction operations SaaS product.
The backend is Python 3.13. We need a framework that supports:

- Async I/O (database, object storage, external APIs are all I/O-bound)
- Request/response validation with clear error messages for field-level failures
- OpenAPI documentation auto-generated from code (reduces maintenance drift)
- Type safety compatible with a strict mypy configuration
- Dependency injection for composable auth, DB sessions, and RBAC

The primary alternatives evaluated were Flask, Django REST Framework, and
FastAPI.

---

## Decision

Use **FastAPI** as the web framework.

---

## Rationale

### 1. Native async support

FastAPI is built on Starlette (ASGI), meaning every handler runs in an async
event loop. This is load-bearing for us: we use `asyncpg` for non-blocking
database queries, `aioboto3` for S3, and Redis via async clients. A sync
framework like Flask or DRF would require either threading (higher memory cost)
or wrapping async code in `run_until_complete` (defeats the purpose).

### 2. Pydantic validation is the contract

FastAPI uses Pydantic models as the single source of truth for request bodies,
response shapes, and query parameters. The JSON schema derived from those
models automatically populates the OpenAPI spec. This means documentation stays
in sync with the code by construction — not by discipline.

When a site engineer's mobile app sends a malformed payload, FastAPI + Pydantic
returns a structured 422 with `{"field": "quantity", "message": "must be > 0"}`.
We customise this in `error_handlers.py` to match our envelope format.

### 3. Dependency injection is first-class

FastAPI's `Depends()` system lets us compose:

```python
async def get_current_user(...) -> UserInToken: ...
def require_role(*roles): return Depends(...)

@router.post("/indents")
async def create_indent(
    body: CreateIndentRequest,
    user: UserInToken = Depends(get_current_user),
    _role: None = Depends(require_role("site_engineer", "admin")),
    db: AsyncSession = Depends(get_db),
):
```

This wires auth, RBAC, and DB sessions declaratively at the route level, with
zero boilerplate in the handler body. Django and Flask achieve similar things
via decorators or middleware, but the dependency graph is not as composable or
testable — overriding `get_db` in tests with a transaction-scoped session is
one line: `app.dependency_overrides[get_db] = lambda: test_session`.

### 4. Type annotations throughout

FastAPI was designed for typed Python from day one. Route parameters, response
models, and Depends arguments all participate in mypy's type graph. This
catches bugs (passing an `int` where a `UUID` is expected) at CI time, not
in production.

---

## Alternatives Considered

| Framework | Why Not Chosen |
|---|---|
| **Flask** | Synchronous by default; adding async requires Quart or complex event loop management; no built-in validation or OpenAPI generation |
| **Django REST Framework** | Django's ORM is synchronous and not compatible with `asyncpg`; Django async support is partial (Django 4.2+); significantly more boilerplate for a pure-API project with no templating needs |
| **Litestar** | Younger ecosystem; smaller community; more risk of hitting framework bugs in production with fewer workarounds available |
| **aiohttp** | Provides an async HTTP server but no validation, no dependency injection, no OpenAPI — would require building those ourselves |

---

## Consequences

### Positive
- Async handlers throughout; no threading overhead
- Pydantic validation with structured error responses out of the box
- OpenAPI spec auto-generated; frontend teams can generate SDK clients
- Dependency injection makes unit testing trivial (override any dep)
- Strong type safety; mypy strict mode compatible

### Negative
- FastAPI's `dependency_overrides` and `lifespan` are framework-specific; if
  we ever migrated to a different ASGI framework, test infrastructure and the
  DI wiring would need rewriting
- Background tasks (`BackgroundTasks`) in FastAPI have limited visibility; we
  use Celery instead for anything that must be observable or retried — this
  creates two async execution models to understand
- FastAPI does not have a built-in ORM, admin panel, or migration tool —
  each must be added separately (we chose SQLAlchemy + Alembic)

---

## Review Trigger

Revisit if:
- FastAPI's pace of breaking changes between major versions creates migration
  cost that outweighs its benefits
- We need server-side rendering or a built-in admin UI (at which point Django
  becomes more attractive as a unified solution)
