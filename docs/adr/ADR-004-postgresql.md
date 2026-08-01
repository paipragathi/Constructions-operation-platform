# ADR-004: PostgreSQL as the Primary Database

**Status:** Accepted  
**Date:** 2026-08-01  
**Deciders:** Engineering

---

## Context

The platform manages financially significant data: payroll records, purchase
orders, goods receipt notes, RA bills, and budget-vs-actual reports. In India,
construction accounting records are legal evidence — they may be required by
GST auditors, labour inspectors, or arbitration panels. This constrains the
database choice: we need ACID guarantees, a mature audit trail story, and
correctness over performance.

The data model is highly relational: a GRN references a PO which references an
Indent which references a Project, a Site, and a Material catalogue entry. Many
queries join 4–6 tables. We also need complex aggregations (budget-vs-actual,
stock position, payroll summaries) that involve grouping, window functions, and
conditional sums.

---

## Decision

Use **PostgreSQL 16** as the primary database for all transactional data.

---

## Rationale

### 1. ACID guarantees are non-negotiable for financial data

A payroll run that debits one account and credits another must either complete
fully or not at all. A GRN that updates stock must update the ledger atomically.
PostgreSQL's multi-version concurrency control (MVCC) provides serialisable
isolation without locking readers, meaning reporting queries don't block writes
from site engineers.

NoSQL databases (MongoDB, DynamoDB) offer eventual consistency models that are
appropriate for high-write, low-consistency workloads. Payroll is the opposite:
low-write, extremely high-consistency.

### 2. The domain is inherently relational

Construction procurement follows a chain: `Indent → PO → GRN → StockLedger`.
Foreign key constraints enforce this chain at the database level — not just in
application code, which can have bugs. A GRN that references a non-existent PO
is prevented by the DB, not just by the service layer.

`NUMERIC(12,2)` vs `FLOAT`: PostgreSQL's `NUMERIC` type is exact-precision
decimal arithmetic. `FLOAT` is IEEE 754 binary floating point — it cannot
represent 0.1 exactly. For payroll (daily wages × days × deduction rates),
`FLOAT` accumulates rounding errors. We use `NUMERIC(12,2)` for every money
column. PostgreSQL enforces this correctly; MySQL's `DECIMAL` does too, but
with different edge-case behaviour.

### 3. Advanced SQL features we actually use

- **Window functions**: `ROW_NUMBER() OVER (PARTITION BY project_id ORDER BY created_at)` for RA bill numbering
- **CTEs**: budget-vs-actual is a recursive roll-up across cost heads
- **`gen_random_uuid()`**: server-side UUID generation, no extension required since PG 13
- **`pg_stat_statements`**: query-level performance profiling without any app changes
- **Partial indexes**: `WHERE is_deleted = false` on soft-delete tables eliminates the need to scan deleted rows
- **`JSONB`**: semi-structured metadata (custom form fields) stored alongside relational data without a schema change

### 4. `asyncpg` is native to PostgreSQL

asyncpg speaks the PostgreSQL binary protocol directly. It is not a generic
DBAPI2 adapter. This means we get binary data transfer (faster for large
result sets), prepared statement caching, and PostgreSQL-specific types
(UUID, JSONB, ARRAY) without serialisation overhead.

### 5. Operational familiarity and managed service availability

PostgreSQL is available as a managed service on AWS (RDS, Aurora), GCP
(Cloud SQL), and Azure (Flexible Server). Indian cloud providers (Reliance
Jio Cloud, Tata Communications) also offer managed PostgreSQL. On-premises
deployments at larger customers can run standard PostgreSQL. There is no
vendor lock-in on the data layer.

---

## Alternatives Considered

| Database | Why Not Chosen |
|---|---|
| **MySQL / MariaDB** | Weaker MVCC semantics; `DECIMAL` edge cases differ; fewer advanced SQL features; `asyncpg` is PostgreSQL-specific |
| **MongoDB** | Document model is a poor fit for a deeply relational domain; no multi-document ACID transactions in older versions; eventual consistency unacceptable for financial records |
| **SQLite** | No concurrent writers; not suitable for multi-user SaaS; no `gen_random_uuid()` without extension |
| **CockroachDB / Distributed SQL** | Our initial scale does not require distributed SQL; adds operational complexity and licensing cost; PostgreSQL wire-compatible but with subtle behavioural differences |
| **Amazon Aurora** | Aurora is PostgreSQL-compatible and an excellent production choice, but it is an operational decision made at deployment time — the application code targets standard PostgreSQL |

---

## Consequences

### Positive
- ACID transactions for all financial operations
- Foreign key constraints enforce referential integrity at DB level
- `NUMERIC` eliminates payroll rounding errors
- `gen_random_uuid()` available without extensions
- `pg_stat_statements` gives instant query performance visibility
- Portable across all major cloud providers

### Negative
- PostgreSQL requires more operational knowledge than managed NoSQL (backups,
  WAL archiving, vacuum tuning, connection pooling) — mitigated by using
  managed RDS or Aurora in production
- Connection-per-request model (even with pooling via asyncpg) limits
  parallelism to pool size — use PgBouncer in front of PostgreSQL for very
  high concurrency; revisit at >500 concurrent users

---

## Review Trigger

Revisit if:
- A specific reporting query (e.g., cross-project budget roll-up) exceeds
  acceptable latency even after indexing — at that point, consider a
  separate read replica or a lightweight OLAP layer (e.g., DuckDB)
- We need full-text search over document attachments — PostgreSQL's `tsvector`
  is adequate for basic cases; Elasticsearch or Typesense for advanced
