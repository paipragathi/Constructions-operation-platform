# ADR-005: Multi-Tenancy via Shared Schema with organization_id

**Status:** Accepted  
**Date:** 2026-08-01  
**Deciders:** Engineering

---

## Context

This is a SaaS product targeting multiple construction companies (tenants).
Each company's data must be completely isolated from every other company's data.
A site engineer at Sharma Constructions must never see a GRN from Reddy Builders.

There are three standard approaches to multi-tenancy in a relational database:
1. **Separate databases** — one PostgreSQL database per tenant
2. **Separate schemas** — one PostgreSQL schema per tenant in the same database
3. **Shared schema** — all tenants in the same tables, distinguished by a
   `organization_id` column

We are starting with a small number of tenants (target: 50 within 12 months,
5,000 within 3 years) and a lean engineering team.

---

## Decision

Use **shared schema multi-tenancy**: every business table carries an
`organization_id` column, enforced by the `TimestampedBase` abstract model.
All queries filter on `organization_id`.

```python
class TimestampedBase(Base):
    __abstract__ = True
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
```

The repository layer enforces this: no public method on `BaseRepository`
returns results without filtering on `organization_id`.

---

## Rationale

### 1. Operational simplicity at current scale

Separate databases require: per-tenant connection strings, per-tenant Alembic
migration runs, per-tenant backup schedules, per-tenant connection pools.
At 5,000 tenants, that is 5,000 databases to monitor. Separate schemas are
slightly better but still require per-tenant migration scripts and schema
creation automation.

Shared schema means one database, one migration run, one backup, one
connection pool. Operations complexity is O(1) in tenant count.

### 2. Column-level isolation is enforced in the repository layer

The risk with shared schema is a query that forgets the `organization_id` filter.
We mitigate this architecturally:

- `BaseRepository.get_by_id(id, organization_id)` — the org_id is a required
  parameter, not optional
- `BaseRepository.list_all(organization_id, ...)` — same
- No raw SQL in service layer; all queries go through the repository
- Tests for any new endpoint assert that cross-tenant data is not returned

This is defence in depth: even if a developer writes a buggy service-layer query,
the repository enforces the filter.

### 3. Index strategy accounts for org scoping

Every business table has a composite index `(organization_id, ...)` on the
columns that are frequently filtered. Queries like "all active projects for
org X" hit the index directly — no full-table scan.

```sql
-- Index on users table
CREATE INDEX ix_users_org_active ON users (organization_id, is_active);
```

PostgreSQL's query planner uses this composite index when both columns appear
in the WHERE clause, giving O(log n) lookup per tenant even as total row count
grows.

### 4. Future migration path to separate schemas is clear

If a large enterprise customer requires data isolation at the schema or database
level (regulatory requirement, contractual obligation), the migration path from
shared schema is:
1. Export all rows for that tenant
2. Create a separate database/schema
3. Import rows
4. Update their connection string in the platform configuration

This is a one-time migration per customer, not a redesign. Starting with separate
databases and consolidating is far harder.

---

## Alternatives Considered

| Strategy | Why Not Chosen |
|---|---|
| **Separate databases per tenant** | O(n_tenants) operational complexity; connection pool per tenant; migration automation required; significant overhead before reaching 100 tenants |
| **Separate PostgreSQL schemas** | Better isolation than shared schema but still O(n_tenants) for migrations; SQLAlchemy schema support (`__table_args__ = {"schema": tenant_slug}`) requires dynamic schema switching which complicates the ORM significantly |
| **Row-level security (PostgreSQL RLS)** | Enforces tenant isolation at the DB level — extremely robust. Rejected for now because it requires setting a session variable (`SET app.current_org = '...'`) on every connection, which is incompatible with the asyncpg connection pool's connection reuse model without careful reset-on-return logic. Worth revisiting for high-assurance enterprise tiers. |

---

## Consequences

### Positive
- One migration run updates all tenants atomically
- One backup covers all tenants
- One connection pool; no per-tenant resource allocation
- Simple to reason about: every query has `WHERE organization_id = $1`
- Infrastructure scales with data volume, not tenant count

### Negative
- A bug that omits `organization_id` from a query leaks cross-tenant data —
  partially mitigated by repository enforcement, but not by the DB itself
- A single noisy tenant (extremely large query, many rows) can affect p99
  latency for other tenants — mitigate with statement timeout and rate limiting
- Enterprise customers requiring contractual data isolation cannot be served
  without a separate deployment or schema migration

---

## Security Invariants (must never be violated)

1. Every `SELECT`, `UPDATE`, `DELETE` that touches a business table **must**
   include `WHERE organization_id = :org_id`
2. The `organization_id` in every query must come from the **decoded JWT**, not
   from a request body or URL parameter
3. Integration tests must include at least one test per endpoint that creates
   data for org A and asserts org B cannot retrieve it

---

## Review Trigger

Revisit if:
- A regulatory customer (bank, government) requires contractual database-level
  isolation — at that point, add a "dedicated tier" with a separate schema or
  database, keeping shared schema for the standard tier
- PostgreSQL Row-Level Security can be made compatible with the asyncpg
  connection pool model without performance penalty
