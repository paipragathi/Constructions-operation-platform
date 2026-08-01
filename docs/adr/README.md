# Architecture Decision Records

This directory documents the significant architectural decisions made for the
Construction Site Operations Platform. Each ADR captures the context, the
decision, the reasoning, and the trade-offs — written at the time the decision
was made.

ADRs are not living documents. Once accepted, an ADR is not edited to reflect
later changes. If a decision is reversed or superseded, a new ADR is written
that references the old one and explains what changed and why.

---

## Index

| ADR | Decision | Status |
|-----|----------|--------|
| [ADR-001](ADR-001-uuid-over-bigserial.md) | UUID over BIGSERIAL for primary keys | Accepted |
| [ADR-002](ADR-002-why-fastapi.md) | FastAPI as the web framework | Accepted |
| [ADR-003](ADR-003-sqlalchemy-async.md) | SQLAlchemy 2.x async with asyncpg | Accepted |
| [ADR-004](ADR-004-postgresql.md) | PostgreSQL as the primary database | Accepted |
| [ADR-005](ADR-005-multi-tenancy.md) | Multi-tenancy via shared schema with organization_id | Accepted |
| [ADR-006](ADR-006-jwt-authentication.md) | JWT access tokens + opaque refresh tokens | Accepted |
| [ADR-007](ADR-007-repository-pattern.md) | Repository pattern for data access | Accepted |
| [ADR-008](ADR-008-service-layer.md) | Service layer for business logic | Accepted |
| [ADR-009](ADR-009-invitation-flow.md) | Token-based invitation flow | Accepted |
| [ADR-010](ADR-010-project-status-machine.md) | Project status state machine | Accepted |

---

## Format

Each ADR follows this structure:

- **Context** — what problem were we solving; what constraints existed
- **Decision** — what we chose, with a code snippet where helpful
- **Rationale** — why, including alternatives evaluated and rejected
- **Consequences** — positive and negative trade-offs
- **Review Trigger** — specific conditions under which this decision should be revisited

---

## How to Add a New ADR

1. Copy an existing ADR as a template
2. Name it `ADR-NNN-short-description.md` (next sequential number)
3. Set status to `Proposed` until the team agrees
4. Update this index
5. Commit it alongside the code change it documents
