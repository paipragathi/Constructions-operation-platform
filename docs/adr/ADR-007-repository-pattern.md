# ADR-007: Repository Pattern for Data Access

**Status:** Accepted  
**Date:** 2026-08-01  
**Deciders:** Engineering

---

## Context

We have three layers that need to interact with the database:
1. Route handlers (API layer) — handle HTTP, validate input, return responses
2. Business logic — enforce rules, coordinate changes across tables
3. Data access — translate domain operations into SQL

Without a deliberate structure, these three concerns collapse together: route
handlers start calling `session.execute(select(...))` directly, business logic
gets embedded in SQL queries, and tests require a real database to verify any
behaviour.

We need a pattern that:
- Isolates the SQLAlchemy API surface to one layer
- Makes `organization_id` scoping impossible to forget
- Allows service layer and API handlers to be unit-tested with fakes
- Does not introduce unnecessary abstraction for simple CRUD operations

---

## Decision

Use the **Repository Pattern**: one class per aggregate root, with a
`BaseRepository[T]` generic that provides common CRUD operations. All
SQLAlchemy queries live inside repositories. No `session.execute` calls
outside of `app/repositories/`.

```
API handler
    ↓ calls
Service
    ↓ calls
Repository
    ↓ executes SQL via
AsyncSession
```

---

## Rationale

### 1. organization_id enforcement is structural, not optional

The worst possible failure in a multi-tenant system is a cross-tenant data
leak. If every developer writes their own `select(Model).where(...)` queries,
the `organization_id` filter is applied only if they remember it.

With `BaseRepository`, forgetting is structurally harder:

```python
async def get_by_id(self, id: UUID, organization_id: UUID) -> Model | None:
    return await self.session.execute(
        select(self.model).where(
            self.model.id == id,
            self.model.organization_id == organization_id,  # always here
            self.model.is_deleted.is_(False),
        )
    )
```

`organization_id` is a positional argument, not a keyword argument — you
cannot call this method without providing it. The API surface makes the safe
path the default path.

### 2. The service layer has no idea how data is stored

A service method like `auth_service.login()` calls
`user_repository.get_active_by_email(email)`. It does not know whether that
translates to:
- A PostgreSQL query
- A Redis cache lookup with a fallback to PostgreSQL
- A test stub that returns a fixture

This makes the service layer testable with a simple fake:

```python
class FakeUserRepository:
    async def get_active_by_email(self, email: str) -> User | None:
        return self._users.get(email)
```

No test database, no testcontainers, no migration: just a dict.

### 3. SQL changes don't ripple into business logic

If we add an index, change a query plan hint, or switch from a subquery to
a join for performance, only the repository changes. The service layer and
API handlers are unaffected. This makes performance tuning much less
risky — there is exactly one place per model where each query lives.

### 4. Transactions are owned by the service layer, not the repository

Repositories call `session.flush()` (write to transaction buffer) but not
`session.commit()` (write to disk). The `get_db` dependency commits the
session after the handler returns. This means:

```python
async def login(self, ...):
    user = await self._users.get_active_by_email(email)
    # business logic...
    refresh = RefreshToken(...)
    await self._tokens.create(refresh)       # flush only
    await self._users.update_last_login(...)  # flush only
    return TokenResponse(...)
    # get_db commits both writes atomically after this returns
```

If `update_last_login` raises, `create(refresh)` is also rolled back.
Atomicity is guaranteed by the outer transaction, not by individual repository
calls. This is the key difference from the Active Record pattern, where each
`model.save()` commits immediately.

---

## What the Repository Is NOT

- **Not a query builder facade**: complex reporting queries (budget-vs-actual,
  payroll summaries) should be in specialised query methods on the appropriate
  repository, not assembled in the service layer using chainable filter methods
- **Not a unit of work**: the session (`get_db`) is the unit of work; the
  repository is just the query object for one model
- **Not an abstraction over multiple databases**: we have one PostgreSQL instance;
  the repository is not designed to swap backends

---

## Alternatives Considered

| Approach | Why Not Chosen |
|---|---|
| **Active Record (SQLAlchemy models call save/delete directly)** | Business logic migrates into the model; models become fat; `session.commit()` scattered everywhere; impossible to batch writes in a single transaction without contortions |
| **Data Mapper without a dedicated repository class** | Service layer calls `session.execute()` directly; `organization_id` filter discipline is manual; SQLAlchemy API surface leaks into every layer |
| **Calling `session.execute()` from route handlers** | Maximum coupling; testing requires a real database for any test; business logic ends up in route handlers |
| **Generic ORM-based repository (e.g., sqlalchemy-repository)** | Third-party library adds a dependency; we needed org_id enforcement as a first-class concept, which generic libraries don't provide |

---

## Consequences

### Positive
- `organization_id` is structurally enforced in all queries
- Service layer has no SQLAlchemy dependency — testable with fakes
- One place to look for any query: the relevant repository file
- Transactional consistency is managed by the session, not by individual
  repository calls

### Negative
- Boilerplate: every new aggregate needs a new repository class, even if it
  only needs `get_by_id` and `create` — partially mitigated by `BaseRepository`
- Developers unfamiliar with the pattern may try to add query logic in the
  service layer; code review must catch this
- The indirection adds a layer to trace when debugging unexpected query results

---

## Review Trigger

Revisit if:
- A significant portion of endpoints are purely CRUD with no business logic —
  in that case, consider whether the service layer adds value or is just a
  pass-through (and possibly collapse service + repository for those endpoints)
