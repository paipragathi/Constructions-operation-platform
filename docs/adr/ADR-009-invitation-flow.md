# ADR-009: Token-Based Invitation Flow

**Status:** Accepted  
**Date:** 2026-08-01  
**Deciders:** Engineering

---

## Context

Users cannot self-register on this platform. Every user belongs to exactly one
organization, and only an admin of that organization can grant access. We need
a mechanism where:

1. An admin creates an invitation for a specific email + role
2. The invitee receives a link, proves they own the email, sets a password, and
   is granted access
3. The invitation expires if unused
4. The invitation cannot be reused after acceptance

Three standard approaches exist: secure token links, time-based OTPs (TOTP),
and magic links (passwordless). This decision documents which we chose and why.

---

## Decision

Use a **single-use, time-limited, SHA-256-hashed token** sent via email as a
URL parameter. The recipient clicks the link, which validates the token and
allows them to set a password and complete registration.

```
Admin: POST /users/invite { email, role }
         ↓
System creates Invitation { token_hash, expires_at: +7 days }
         ↓
Email sent: "Accept your invitation → /accept?token=<raw_token>"
         ↓
Invitee: GET /invitations/validate?token=<raw_token>  (check valid + not expired)
         ↓
Invitee: POST /invitations/accept { token, full_name, password }
         ↓
System: creates User, marks invitation accepted_at = now()
         ↓
Invitee: can now login normally via POST /auth/login
```

Token properties:
- 64 hex characters (32 bytes = 256 bits of entropy)
- Stored as `SHA-256(raw_token)` in the database — raw token never persisted
- Expires in 7 days
- Single-use: `accepted_at IS NOT NULL` means used

---

## Rationale

### 1. Why token over TOTP

TOTP (6-digit time-based codes) requires the user to enter the code within a
30-second or 5-minute window. For an invitation that was sent 2 hours ago to a
busy project manager, that is a poor UX — they would need to request a new
code. A 7-day token means the link works whenever the invitee gets around to it.

TOTP is appropriate for 2FA (user-initiated, short window by design). It is not
appropriate for async invitation flows.

### 2. Why token over magic link (passwordless)

A magic link *is* a token link, but it logs the user in directly without
setting a password. For our platform, that creates a problem: the next time the
user wants to log in, they need another magic link. We want users to set a
password once and use it repeatedly — mobile apps on construction sites cannot
wait for email delivery every login.

We use a token for *onboarding* (one-time) and password for *authentication*
(ongoing). These are separate concerns that should not share a mechanism.

### 3. Why hash the token in the database

The raw token is a credential. If an attacker dumps the `invitations` table,
they should not be able to impersonate an invitee and accept their invitation.
SHA-256 of a 256-bit random value is computationally irreversible.

The argument "it's just an invitation, not a password" understates the risk:
accepting an invitation creates a User account with the email and role specified
by the admin. A stolen invitation token is effectively a stolen account-creation
credential.

We use SHA-256 (not bcrypt) for the same reason as refresh tokens: the input
has 256 bits of entropy, so brute-force is infeasible; bcrypt's cost is
unnecessary for high-entropy values.

### 4. Why 7 days expiry

Construction project managers are busy. An invitation sent on Monday may not
be noticed until Thursday. 24 hours is too short; 30 days is too long for a
security-sensitive link. 7 days (one work week) is the natural unit for a B2B
construction platform.

Expired invitations can be re-sent by the admin (which generates a new token).

### 5. Invite-only vs self-registration

Self-registration would allow anyone to create an account for any organization
by guessing or scraping the `organization_slug`. In a multi-tenant B2B context
where data isolation is critical, invite-only is the correct default. If we
later want self-registration (e.g., for a freemium tier), we add it as an
explicitly enabled organization setting.

---

## What the invitation is NOT

- Not a login mechanism: it is used once, then the user authenticates with a
  password
- Not an email verification mechanism: we trust that the admin knows the
  correct email for their team member
- Not re-sendable as-is: re-inviting generates a new token; old one is
  invalidated (or left to expire)

---

## Alternatives Considered

| Approach | Why Not Chosen |
|---|---|
| TOTP (6-digit code) | Too short a window for async invitation; user must be available at the moment they check email |
| Magic link (passwordless) | Creates a login dependency on email delivery; incompatible with mobile-first field use |
| Admin creates password on behalf of user | Admin knows the user's temporary password — a security anti-pattern; requires a password-change-on-first-login enforcement mechanism |
| OAuth2 sign-in (Google, GitHub) | Requires the invitee to have a Google/GitHub account; not guaranteed for Indian construction SMB employees |

---

## Consequences

### Positive
- Invitee owns their own password from day one
- Token is usable any time within 7 days
- SHA-256 hash protects against DB dump attacks
- Flow is familiar to users of any SaaS product

### Negative
- Email delivery is a dependency: if email doesn't arrive, the invitation is
  lost until the admin resends — mitigate with a "resend" endpoint and delivery
  status logging
- 7-day tokens that are never accepted accumulate in the table — pruned by the
  existing nightly Celery cleanup task

---

## Review Trigger

Revisit if:
- A customer's IT security policy prohibits token links in email (at which
  point, offer TOTP as an alternative)
- We add SSO/SAML for enterprise customers, at which point invitation flow
  may be replaced by IdP-driven provisioning (SCIM)
