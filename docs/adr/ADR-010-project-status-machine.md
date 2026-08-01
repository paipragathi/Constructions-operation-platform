# ADR-010: Project Status State Machine

**Status:** Accepted  
**Date:** 2026-08-01  
**Deciders:** Engineering

---

## Context

A construction project is not a static record — it moves through defined phases
over its lifetime. Operations that are valid in one phase are invalid in another:
you cannot raise an indent on a closed project; you cannot mark attendance at a
site if its project is on hold. The application needs to model these lifecycle
states and enforce the allowed transitions.

The same problem recurs throughout the platform: Material Indents, Purchase
Orders, GRNs, and RA Bills all have their own state machines. The design
decision made here becomes the template for all of them.

---

## Decision

Model project status as a **plain string column** with a defined set of allowed
values and an explicit transition table enforced in the service layer.

### States

```
DRAFT → ACTIVE → ON_HOLD → ACTIVE
                ↓         ↓
              CLOSED ← ON_HOLD
```

| State | Meaning |
|-------|---------|
| `draft` | Project created, not yet started — no site operations allowed |
| `active` | Work in progress — all operations allowed |
| `on_hold` | Work paused (weather, client hold, dispute) — no new indents/attendance |
| `closed` | Project complete — immutable, no further operations |

### Allowed transitions

```python
ALLOWED_TRANSITIONS = {
    "draft":   {"active"},
    "active":  {"on_hold", "closed"},
    "on_hold": {"active", "closed"},
    "closed":  set(),  # terminal state
}
```

### Enforcement (service layer)

```python
def _validate_transition(self, current: str, next: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if next not in allowed:
        raise InvalidStatusTransitionError(
            f"Cannot transition project from '{current}' to '{next}'"
        )
```

---

## Rationale

### 1. Why a string column, not a PostgreSQL ENUM

PostgreSQL ENUMs are fast and enforce values at the DB level, but adding a new
value requires `ALTER TYPE ... ADD VALUE`, which:
- Cannot be run inside a transaction in PostgreSQL < 12
- Cannot be rolled back even in PG 12+ in certain contexts
- Requires a migration for every new status value

A `VARCHAR(20)` column with a `CHECK` constraint (or just application-level
enforcement) is equally fast for our read patterns and requires only a simple
migration to add a new state. We enforce the allowed values as a Python constant
— that's sufficient given our service-layer pattern.

### 2. Why four states, not two (active / closed)

"Active" conflates two meaningfully different conditions: a project that hasn't
started yet (`draft`) and one that is actively underway. In practice:
- A `draft` project should not accept indents or attendance records — data
  entered before the project is formally active is pre-production noise
- An `on_hold` project needs to be distinguishable from a `closed` one for
  reporting ("how many projects are currently paused?")

Four states map to real construction business states without over-engineering.

### 3. Why closed is a terminal state with no exit

In Indian construction contracts, a "closed" project triggers financial
settlements: final RA bills, security deposit release, defect liability period.
Reopening a closed project would create ambiguity about which financial records
are final. If a closed project genuinely needs to be reactivated (rare),
that should require an admin action with an explicit reason — not a routine
status toggle. We model `closed` as terminal; the rare reopen case can be
handled with a `POST /projects/{id}/reopen` endpoint added when the need arises.

### 4. Why enforcement is in the service layer, not the database

The transition rules are business logic. A database CHECK constraint would
enforce "status must be one of these values" but not "from state X, only Y and
Z are allowed." That conditional logic belongs in `ProjectService`, where it
can be tested independently, where error messages can be domain-specific, and
where it can be composed with other checks (e.g., "cannot close a project with
open POs").

### 5. This pattern is the template for all other state machines

The same structure — string column, Python dict of allowed transitions, service
enforcement — will be used for:
- Material Indent: `draft → submitted → approved / rejected`
- Purchase Order: `draft → issued → partially_received → closed`
- GRN: `draft → submitted → approved`
- RA Bill: `draft → submitted → approved → paid`

Establishing the pattern in Sprint 2 means every future state machine is
immediately recognisable to any developer on the team.

---

## Business rules layered on top of state

These are enforced in the service layer alongside the transition check:

| Operation | Requires project state |
|-----------|----------------------|
| Raise a material indent | `active` |
| Mark attendance | `active` |
| Create a site | `draft` or `active` |
| Generate an RA bill | `active` or `on_hold` |
| Close a project | No open indents, no open POs |

---

## Alternatives Considered

| Approach | Why Not Chosen |
|---|---|
| PostgreSQL ENUM type | Adding states requires DDL changes that cannot be transactional; operational friction outweighs type-safety benefit |
| Separate `project_states` table with FK | Adds a join to every project query for no benefit beyond what a string column provides; over-normalised |
| Boolean `is_active` / `is_closed` | Multiple booleans create invalid combinations (`is_active=True, is_closed=True`); not extensible |
| Finite State Machine library (e.g., `transitions`) | Adds a dependency for logic that is 8 lines of Python; defer until the state machines become complex enough to warrant it |

---

## Consequences

### Positive
- Adding a new state is a Python constant change + migration (no DDL type change)
- Transition logic is in one method, one file — easy to test
- Pattern is reusable across all workflow entities
- Error messages can include domain vocabulary ("Cannot close project with open purchase orders")

### Negative
- The DB column accepts any string — application must never bypass the service
  layer to update `status` directly (enforced by code review and the repository
  pattern)
- No DB-level enforcement of transition ordering (acceptable given service layer
  is the single write path)

---

## Review Trigger

Revisit if:
- State machines grow beyond 6–7 states or require parallel states (project is
  both `active` and `under_dispute`) — at that point, consider a proper FSM
  library or a dedicated `project_state_transitions` audit table
