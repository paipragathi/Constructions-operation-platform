"""
Security utilities: JWT and password hashing.

JWT design:
  - Minimal payload: sub, role, org_id, jti, exp, iat
  - No site_id, no project_ids — these change and would make the token stale
  - Access token: short-lived (8 hours), stateless, verified on every request
  - Refresh token: long-lived (30 days), stored in DB, rotated on use

Password hashing:
  - bcrypt with work factor 12 (cost high enough to resist brute force,
    low enough not to slow down logins noticeably — ~250ms per hash)
  - Never store plaintext passwords anywhere, including logs
"""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import TokenExpiredError, TokenInvalidError


# ── Password Hashing ───────────────────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    """
    Hash a plaintext password using bcrypt.
    Work factor 12 means ~250ms per hash on modern hardware — intentionally slow.
    """
    password_bytes = plaintext.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.
    Uses constant-time comparison to prevent timing attacks.
    Returns False on any error (malformed hash etc.) rather than raising.
    """
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT Access Token ───────────────────────────────────────────────────────────

def create_access_token(
    user_id: uuid.UUID,
    role: str,
    organization_id: uuid.UUID,
) -> str:
    """
    Create a signed JWT access token.

    Payload fields:
      sub  → user UUID (the subject — who this token represents)
      role → user's role string
      org  → organization UUID (tenant scoping)
      jti  → unique token ID (for future revocation if needed)
      iat  → issued-at timestamp
      exp  → expiry timestamp
    """
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    payload: dict[str, object] = {
        "sub": str(user_id),
        "role": role,
        "org": str(organization_id),
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, object]:
    """
    Decode and verify a JWT access token.

    Raises:
      TokenExpiredError  → token's exp is in the past
      TokenInvalidError  → signature invalid, malformed, wrong algorithm
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError as e:
        raise TokenInvalidError(f"Token verification failed: {e}")

    return payload  # type: ignore[return-value]


# ── Refresh Token ──────────────────────────────────────────────────────────────

def generate_refresh_token() -> str:
    """
    Generate an opaque refresh token.

    Refresh tokens are NOT JWTs. They are random 64-byte hex strings stored
    in the database. This means:
      - They can be revoked at any time (delete the DB row)
      - They carry no embedded claims (the server looks up the user on use)
      - Compromise of a refresh token does not expose JWT signing secrets
    """
    return uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars = 32 random bytes


def refresh_token_expiry() -> datetime:
    """Returns the UTC datetime when a newly issued refresh token expires."""
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
