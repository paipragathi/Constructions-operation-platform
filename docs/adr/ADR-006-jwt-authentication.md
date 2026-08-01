# ADR-006: JWT Access Tokens + Opaque Refresh Tokens

**Status:** Accepted  
**Date:** 2026-08-01  
**Deciders:** Engineering

---

## Context

We need an authentication mechanism for a REST API consumed by:
- A web dashboard (React, browser)
- A mobile field app (Android tablets used by site engineers in low-connectivity areas)
- Future third-party integrations

Requirements:
1. Stateless verification — horizontally scaled API servers must be able to
   verify a token without a shared session store
2. Revocability — a compromised account must be lockable without a deploy
3. Appropriate lifetime — site engineers work 10-hour days; requiring re-login
   every hour would disrupt their work
4. Minimal payload — tokens must not embed data that becomes stale mid-session

---

## Decision

Use **short-lived JWT access tokens** (8 hours) for API authorization, paired
with **opaque refresh tokens** stored as SHA-256 hashes in the database.

### Access token payload (minimal)

```json
{
  "sub": "uuid-of-user",
  "role": "site_engineer",
  "org": "uuid-of-organization",
  "jti": "unique-token-id",
  "iat": 1722499200,
  "exp": 1722528000
}
```

**Not included:** `site_id`, `project_ids`, `permissions[]`, `email`, `name`.

### Refresh token storage

```python
# Client receives raw token (64-char hex)
raw_token = generate_refresh_token()  # secrets.token_hex(32)

# Database stores only the hash
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
RefreshToken(user_id=..., token_hash=token_hash, expires_at=...)
```

---

## Rationale

### 1. Why JWT for the access token

JWT allows any API server to verify authenticity using only the shared secret
and the token itself. No database lookup per request. At our expected load (a
few hundred concurrent users), this is not a bottleneck today, but the
architecture scales to thousands of concurrent users without adding a session
lookup to every hot path.

The JWT is signed with HS256 (HMAC-SHA256). We considered RS256 (asymmetric)
but it is only necessary when third-party services need to verify tokens
without sharing a secret. We don't have that requirement yet; HS256 with a
128-bit secret is simpler and equally secure within a single trust boundary.

### 2. Why the access token payload is minimal

Embedding `project_ids: [uuid, uuid, ...]` in the token sounds convenient —
you avoid a DB lookup in every handler. But it creates a freshness problem:
if a project manager is removed from a project mid-session, their token still
grants access until it expires. For financial data (GRNs, POs, payroll), this
is unacceptable.

Instead, the token carries only `sub`, `role`, and `org`. Authorization
decisions that need current data (e.g., "does this user have access to site X?")
go to the database. This is one extra query per sensitive request — acceptable
and correct.

### 3. Why 8-hour access token lifetime

Standard advice is 15 minutes. The reason for the short recommendation is that
if a token is stolen, you want the theft window to be small. But:

- Site engineers work on construction sites, often without WiFi — a token
  refresh requires a network round-trip they may not have
- 15-minute tokens require the mobile app to implement silent refresh logic,
  increasing mobile complexity and battery usage
- The token is transmitted over HTTPS only; the primary theft vector is XSS or
  device theft, not network interception

8 hours (one working shift) is a deliberate product decision for this user
population. If the security posture requirement changes (e.g., enterprise
customer with compliance requirements), this is a single config value:
`ACCESS_TOKEN_EXPIRE_MINUTES`.

### 4. Why opaque refresh tokens (not a refresh JWT)

A refresh JWT would have the same revocation problem as the access JWT: you
cannot invalidate it before its `exp` without a blocklist (which requires a
DB lookup anyway). If a user loses their phone, they should be able to log in
on a new device and have all existing sessions revoked immediately.

With opaque tokens stored as DB rows, revocation is `DELETE FROM refresh_tokens
WHERE user_id = $1` — instant and global.

### 5. Why SHA-256 hash in the database

We store `sha256(raw_token)`, not the raw token itself. If an attacker dumps
the `refresh_tokens` table, they get hashes, not usable tokens. SHA-256 is
appropriate here because:
- The raw token has 256 bits of entropy (not a low-entropy password)
- We are not protecting against brute-force dictionary attacks — we are
  protecting the dump-and-replay attack
- bcrypt is unnecessary (and expensive) for high-entropy random values

### 6. Token rotation on every refresh

When a refresh token is used, the old row is deleted and a new one is inserted.
This limits the replay window: a stolen refresh token can only be used until
the legitimate user refreshes first, at which point the stolen copy is revoked.
This is sometimes called "refresh token rotation" and is the same model used
by Auth0 and Okta.

---

## Libraries

- **PyJWT** for JWT encode/decode — actively maintained, security-focused
- **bcrypt** (rounds=12) for password hashing — not related to tokens; used
  for the `password_hash` column on `User`
- **cryptography** as the backend for PyJWT crypto operations

Rejected: `python-jose` (known security vulnerabilities in past versions,
maintenance concerns).

---

## Alternatives Considered

| Approach | Why Not Chosen |
|---|---|
| **Session cookies + server-side sessions** | Requires a shared session store (Redis) visible to all API instances; works well for browser-first apps but adds state to a stateless API; more complex for mobile clients |
| **API keys only** | Appropriate for M2M; not for human users who have roles and need to be individually revokable |
| **OAuth2 + external IdP (Auth0, Cognito)** | Adds external dependency and per-MAU cost; over-engineered for initial phase; can be adopted later as a social login or SSO layer |
| **Refresh JWT (long-lived)** | Cannot be individually revoked without a blocklist — same operational cost as opaque tokens but without the clarity |

---

## Consequences

### Positive
- Stateless access token verification — no DB hit per API request
- Instant revocation of any or all sessions per user
- Token rotation limits replay attack window
- No sensitive data in the token; role/org changes take effect on next login

### Negative
- 8-hour access token means a revoked user's existing access token remains
  valid for up to 8 hours — acceptable for our current threat model; if
  immediate revocation is required, add a short-lived token blocklist in Redis
- Opaque refresh token lookup is a DB query on every `/auth/refresh` call —
  this endpoint is called rarely (once per 8 hours), so it's not a hot path
- Refresh token rotation can cause "concurrent refresh" race conditions if a
  mobile app retries a refresh request; mitigate with a short grace period or
  idempotency key

---

## Review Trigger

Revisit if:
- An enterprise customer requires SAML/OIDC SSO — at that point, integrate
  an IdP and delegate token issuance
- Immediate access token revocation becomes a hard requirement — add a Redis
  blocklist keyed on `jti` with TTL equal to the access token lifetime
