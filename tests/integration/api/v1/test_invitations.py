"""
Integration tests for invitation endpoints.

Covers: invite, validate, accept, list, revoke, duplicate/conflict guards.

Token strategy: the API does not expose the raw token (it goes in the email).
For validate/accept flow tests, we create invitations directly in the DB
with a known raw token so tests can exercise those endpoints without email.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation

_INVITE_URL = "/api/v1/invitations"
_VALIDATE_URL = "/api/v1/invitations/validate"
_ACCEPT_URL = "/api/v1/invitations/accept"

_KNOWN_RAW_TOKEN = "a1b2c3d4e5f60123456789abcdef01234567890abcdef01234567890abcdef01"


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@pytest_asyncio.fixture
async def pending_invitation(db: AsyncSession, org: Any, admin_user: Any) -> Invitation:
    """Create a pending invitation with a known raw token directly in the DB."""
    inv = Invitation(
        organization_id=org.id,
        email="invitee@example.com",
        role="site_engineer",
        token_hash=_hash_token(_KNOWN_RAW_TOKEN),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin_user.id,
    )
    db.add(inv)
    await db.flush()
    await db.refresh(inv)
    return inv


# ── POST /invitations ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invite_user_returns_201(
    client: AsyncClient, auth_headers: dict, admin_user
) -> None:
    resp = await client.post(
        _INVITE_URL,
        headers=auth_headers,
        json={"email": "newpm@example.com", "role": "project_manager"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "newpm@example.com"
    assert body["role"] == "project_manager"
    assert body["is_pending"] is True
    assert body["is_expired"] is False
    assert "id" in body


@pytest.mark.asyncio
async def test_invite_existing_member_returns_409(
    client: AsyncClient, auth_headers: dict, admin_user
) -> None:
    resp = await client.post(
        _INVITE_URL,
        headers=auth_headers,
        json={"email": "admin@test.com", "role": "project_manager"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "CONFLICT"


@pytest.mark.asyncio
async def test_invite_duplicate_pending_invitation_returns_409(
    client: AsyncClient, auth_headers: dict, pending_invitation
) -> None:
    resp = await client.post(
        _INVITE_URL,
        headers=auth_headers,
        json={"email": "invitee@example.com", "role": "site_engineer"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "CONFLICT"


@pytest.mark.asyncio
async def test_invite_invalid_role_returns_422(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.post(
        _INVITE_URL,
        headers=auth_headers,
        json={"email": "someone@example.com", "role": "superuser"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invite_without_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        _INVITE_URL,
        json={"email": "anon@example.com", "role": "site_engineer"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invite_as_non_admin_returns_403(
    client: AsyncClient, db, org
) -> None:
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    pm = User(
        organization_id=org.id,
        email="pm-inv@test.com",
        full_name="PM User",
        password_hash=hash_password("Test1234!"),
        role=UserRole.PROJECT_MANAGER,
    )
    db.add(pm)
    await db.flush()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "pm-inv@test.com", "password": "Test1234!"},
    )
    token = login.json()["access_token"]

    resp = await client.post(
        _INVITE_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "new@example.com", "role": "site_engineer"},
    )
    assert resp.status_code == 403


# ── GET /invitations/validate ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_valid_token_returns_is_valid_true(
    client: AsyncClient, pending_invitation, org
) -> None:
    resp = await client.get(_VALIDATE_URL, params={"token": _KNOWN_RAW_TOKEN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_valid"] is True
    assert body["email"] == "invitee@example.com"
    assert body["role"] == "site_engineer"
    assert body["organization_name"] == org.name


@pytest.mark.asyncio
async def test_validate_invalid_token_returns_is_valid_false(
    client: AsyncClient
) -> None:
    resp = await client.get(_VALIDATE_URL, params={"token": "totally-invalid-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_valid"] is False


# ── POST /invitations/accept ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_accept_invitation_creates_user_who_can_login(
    client: AsyncClient, pending_invitation
) -> None:
    accept_resp = await client.post(
        _ACCEPT_URL,
        json={
            "token": _KNOWN_RAW_TOKEN,
            "full_name": "New Engineer",
            "password": "NewPass123!",
        },
    )
    assert accept_resp.status_code == 200
    assert "created" in accept_resp.json()["message"].lower()

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "invitee@example.com", "password": "NewPass123!"},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


@pytest.mark.asyncio
async def test_accept_invitation_twice_returns_401(
    client: AsyncClient, pending_invitation
) -> None:
    first = await client.post(
        _ACCEPT_URL,
        json={"token": _KNOWN_RAW_TOKEN, "full_name": "First Accept", "password": "Pass1234!"},
    )
    assert first.status_code == 200

    second = await client.post(
        _ACCEPT_URL,
        json={"token": _KNOWN_RAW_TOKEN, "full_name": "Second Try", "password": "Pass1234!"},
    )
    assert second.status_code == 401
    assert second.json()["error"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_accept_nonexistent_token_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        _ACCEPT_URL,
        json={"token": "ghost-token-that-does-not-exist", "full_name": "Ghost", "password": "Pass1234!"},
    )
    assert resp.status_code == 401


# ── GET /invitations ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_invitations_returns_created_invitation(
    client: AsyncClient, auth_headers: dict, pending_invitation
) -> None:
    resp = await client.get(_INVITE_URL, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    emails = [inv["email"] for inv in body]
    assert "invitee@example.com" in emails


# ── DELETE /invitations/{id} ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoke_invitation_returns_200(
    client: AsyncClient, auth_headers: dict, pending_invitation
) -> None:
    resp = await client.delete(
        f"{_INVITE_URL}/{pending_invitation.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "revoked" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_revoke_nonexistent_invitation_returns_404(
    client: AsyncClient, auth_headers: dict
) -> None:
    fake_id = "00000000-0000-0000-0000-000000000001"
    resp = await client.delete(f"{_INVITE_URL}/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404
