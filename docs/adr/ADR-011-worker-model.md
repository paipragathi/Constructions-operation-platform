# ADR-011: Worker Data Model Design

**Date:** 2026-08-02  
**Status:** Accepted  
**Deciders:** Founding Engineering Team

---

## Context

Construction sites employ daily-wage workers with specific trade skills (mason, carpenter, electrician, etc.). Workers are distinct from Users — they don't log in, they are managed by site engineers and project managers. We need to store:

1. Worker identity and trade information
2. Government-issued documents (Aadhaar, PAN, Labour Card) for compliance
3. Banking details for salary disbursement
4. PF/ESI registration numbers for statutory compliance

Three design decisions needed:

- **A.** How to model worker trades and skill levels (enum table vs string constants)
- **B.** How to handle worker documents before S3 is available (Sprint 6)
- **C.** How to model document verification

---

## Decision A: Trades and Skill Levels as String Constants

**Chosen:** String constants in Python (same pattern as `UserRole`)  
**Rejected:** Separate `trades` lookup table with foreign keys

### Rationale

- Trade list is stable and small (10-15 values). Construction trades do not change frequently.
- A lookup table adds a JOIN to every worker query with no material benefit.
- ADR-007 (repository pattern) already establishes that validation belongs in the service/schema layer, not the DB schema.
- If a new trade is needed, it is a one-line Python change, not a migration.

**Trade values:** `mason`, `carpenter`, `electrician`, `plumber`, `painter`, `welder`, `tile_layer`, `steel_fixer`, `helper`, `supervisor`, `watchman`, `cleaner`  
**Skill levels:** `unskilled`, `semi_skilled`, `skilled`, `highly_skilled`

---

## Decision B: Document Records as DB Rows with file_key Placeholder

**Chosen:** `worker_documents` table with a `file_key` column (nullable until Sprint 6)  
**Rejected:** Wait until S3 is ready before modelling documents at all

### Rationale

- Document metadata (Aadhaar number, document type, who uploaded it) is valuable now regardless of whether we store the file itself.
- Compliance reporting needs to list which workers have which documents on file — a query the DB can answer today.
- `file_key` is nullable in Sprint 3. Sprint 6 populates it via a pre-signed S3 upload URL flow. The column shape is stable: `VARCHAR(500)` accommodates both MinIO object keys and S3 ARNs.
- No data migration needed when Sprint 6 arrives — rows already exist, Sprint 6 just fills the `file_key`.

---

## Decision C: Document Verification as a Column Triplet

**Chosen:** `verified BOOLEAN`, `verified_by UUID`, `verified_at TIMESTAMPTZ` on `worker_documents`  
**Rejected:** Separate `document_verifications` audit table

### Rationale

- Construction compliance requires knowing *whether* and *when* a document was verified — not a full audit history of every re-verification.
- A triplet (verified + verified_by + verified_at) captures the authoritative state without the JOIN overhead of a separate table.
- If audit history becomes a requirement (Sprint 14), we can add a `document_verification_log` table without altering existing queries.
- Verification can only move from `False → True` via the verify endpoint. Unverification (rolling back) is not a business requirement identified at this stage.

---

## Consequences

- `worker_documents.file_key` is nullable until Sprint 6; API consumers must tolerate `null` for this field.
- Workers are org-scoped (`organization_id` on every row); cross-tenant isolation is enforced by `BaseRepository` exactly as for projects/sites.
- Employee codes (`employee_code`) are unique per organization, enforced via `(organization_id, employee_code)` composite unique index.
- Workers do not have login credentials — they are never Users. If a worker needs portal access (e.g., to view payslips), that is a separate future feature requiring a distinct worker-portal auth flow.
