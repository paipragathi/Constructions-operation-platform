# ADR-008: Service Layer for Business Logic

**Status:** Accepted  
**Date:** 2026-08-01  
**Deciders:** Engineering

---

## Context

The application has business rules that don't belong in either the HTTP layer
or the database layer. Examples:

- "A GRN quantity cannot exceed the outstanding PO quantity"
- "A user cannot approve an indent they created (self-approval prevention)"
- "Payroll for a period cannot be processed if it has already been processed"
- "An indent can only transition from `draft → submitted → approved`, never `approved → draft`"
- "Login must succeed even when the user does not exist, to prevent timing attacks"

These rules span multiple entities, require coordinating writes across tables,
and involve business-specific vocabulary. They do not belong in a repository
(which is agnostic to rules) or in a route handler (which is concerned with
HTTP semantics, not business semantics).

---

## Decision

Implement a **service layer** — one class per domain aggregate or use case —
that contains all business logic. Services:

1. Take plain Python objects as input (not HTTP requests)
2. Call repositories for data access
3. Raise domain exceptions (not `HTTPException`)
4. Return domain objects or DTOs (not `Response` objects)
5. Never import from `fastapi` or `starlette`

```python
class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)

    async def login(self, email: str, password: str, ...) -> TokenResponse:
        user = await self._users.get_active_by_email(email)
        password_ok = verify_password(password, user.password_hash) if user else False
        if not user or not password_ok:
            raise AuthenticationError("Invalid email or password")
        ...
```

The route handler is responsible only for HTTP concerns:

```python
@router.post("/auth/login")
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    return await service.login(email=body.email, password=body.password, ...)
```

---

## Rationale

### 1. The critical rule: services never raise HTTPException

`HTTPException` is a FastAPI/Starlette construct. If a service raises it, the
service is now coupled to the HTTP transport layer. You cannot reuse that
service from a Celery task, a CLI command, or a test without spinning up an
HTTP context.

Instead, services raise domain exceptions:
```python
raise AuthenticationError("Invalid email or password")   # 401
raise NotFoundError(resource="indent", identifier=str(id))  # 404
raise BusinessRuleViolationError("Cannot self-approve")      # 422
```

The global exception handler in `error_handlers.py` maps these to the right
HTTP status codes. The mapping lives in exactly one place.

### 2. Business rules are easier to test when they're not entangled with HTTP

Testing a service method requires:
```python
service = AuthService(fake_db_session)
result = await service.login("user@test.com", "wrong_password")
# AssertionError: AuthenticationError raised
```

Testing the same logic in a route handler requires:
```python
response = await client.post("/auth/login", json={...})
assert response.status_code == 401
```

The route handler test proves the HTTP wiring is correct. The service test
proves the business logic is correct. Both are necessary; neither should do
the other's job.

### 3. The timing attack example demonstrates why the rule matters

A naive login implementation:
```python
user = await db.get_by_email(email)
if not user:
    raise AuthenticationError(...)  # fast path — no bcrypt
password_ok = verify_password(password, user.password_hash)  # slow — bcrypt
if not password_ok:
    raise AuthenticationError(...)
```

An attacker can distinguish "email not found" (fast response) from
"wrong password" (slow response) via timing. The fix:

```python
user = await self._users.get_active_by_email(email)
password_ok = verify_password(password, user.password_hash) if user else False
if not user or not password_ok:
    raise AuthenticationError("Invalid email or password")
```

This security invariant is a business rule. It belongs in the service layer,
not in the route handler. A developer who reviews the route handler might
not think to check for timing attacks. A developer who reviews `auth_service.py`
is looking at auth logic and will notice.

### 4. Services are the correct place for cross-table writes

When a user logs in, three things happen atomically:
1. Look up the user
2. Create a refresh token row
3. Update `last_login_at`

If this logic were in the route handler, the handler would need to import
from both repositories, understand the refresh token model, and coordinate
the flush order. The handler becomes a 50-line function doing auth and HTTP.

In the service layer, the handler is 5 lines; the service is self-contained.

### 5. Services are instantiated per-request, not as singletons

```python
service = AuthService(db)
```

The `db` session is request-scoped. The service holds a reference to it.
After the request, the session is committed and closed. No shared mutable state.

---

## What the Service Layer Is NOT

- **Not an ORM wrapper**: services don't call `session.execute()` — that's the
  repository's job
- **Not a God class**: `AuthService` handles auth. A future `IndentService`
  handles indent lifecycle. `PayrollService` handles payroll runs. Each service
  has a narrow, named responsibility
- **Not required for every route**: if a route is purely reading a single resource
  with no business logic, a thin service method is still preferred (it keeps the
  pattern consistent and makes it testable), but a direct repository call from
  the handler is acceptable for read-only operations

---

## Alternatives Considered

| Approach | Why Not Chosen |
|---|---|
| **Logic in route handlers ("fat controllers")** | Business logic scattered across many endpoint files; untestable without HTTP context; impossible to reuse from Celery tasks or CLI |
| **Logic in models ("fat models" / Active Record)** | Models become stateful and hard to test; domain logic mixed with persistence concerns; SQLAlchemy models are already complex enough as mappers |
| **Logic in repositories** | Repositories are query objects — they should not know whether a GRN quantity exceeds a PO quantity. Mixing query logic with business rules makes the repository hard to reuse and test independently |
| **Separate use-case/command objects** | A more granular alternative (each operation is a class, e.g., `LoginCommand`, `ApproveIndentCommand`). More explicit and DDD-aligned. Rejected as over-engineered for our current scale; the service class is a reasonable mid-point that we can refactor into use-cases later if complexity warrants it |

---

## Consequences

### Positive
- Business logic is concentrated and discoverable: if payroll is broken,
  look in `PayrollService`
- Services are independently testable without HTTP overhead
- Domain exceptions map cleanly to HTTP status codes in one place
- Services can be called from Celery tasks without any HTTP context
- Security rules (timing attack prevention, self-approval check) are in
  code reviewed by domain experts, not buried in route files

### Negative
- One more layer to trace when debugging an end-to-end flow:
  handler → service → repository → DB
- Services are instantiated per-request; for routes with many operations,
  multiple service instantiations are slightly wasteful (negligible in practice)
- Discipline required: developers must not let the service layer "reach up"
  into HTTP concerns or "reach down" into raw SQL — enforced by code review

---

## Review Trigger

Revisit if:
- Services grow beyond ~300 lines, suggesting they are taking on too many
  responsibilities — at that point, split by use case or apply CQRS (separate
  query and command services)
- We introduce a CLI or admin tool that needs to reuse service logic — this is
  actually a validation that the service layer was the right choice
