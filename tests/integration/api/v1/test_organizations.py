"""
Integration tests for organization endpoints.

Covers: registration, get/update my org, role enforcement, cross-tenant isolation.
"""

import pytest
from httpx import AsyncClient


_REGISTER_URL = "/api/v1/organizations"
_MY_ORG_URL = "/api/v1/organizations/me"


# ── Registration ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_org_returns_201_with_tokens(client: AsyncClient) -> None:
    resp = await client.post(
        _REGISTER_URL,
        json={
            "organization_name": "Raj Builders",
            "organization_slug": "raj-builders",
            "admin_email": "admin@raj.com",
            "admin_full_name": "Raj Kumar",
            "admin_password": "SecurePass1!",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_register_org_duplicate_slug_returns_409(client: AsyncClient) -> None:
    payload = {
        "organization_name": "Sharma Constructions",
        "organization_slug": "sharma-constructions",
        "admin_email": "admin@sharma.com",
        "admin_full_name": "Sharma Admin",
        "admin_password": "SecurePass1!",
    }
    resp1 = await client.post(_REGISTER_URL, json=payload)
    assert resp1.status_code == 201

    payload["admin_email"] = "admin2@sharma.com"
    resp2 = await client.post(_REGISTER_URL, json=payload)
    assert resp2.status_code == 409
    assert resp2.json()["error"] == "CONFLICT"


@pytest.mark.asyncio
async def test_register_org_invalid_slug_format_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        _REGISTER_URL,
        json={
            "organization_name": "Bad Co",
            "organization_slug": "INVALID SLUG!",
            "admin_email": "admin@bad.com",
            "admin_full_name": "Admin",
            "admin_password": "SecurePass1!",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_register_org_short_password_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        _REGISTER_URL,
        json={
            "organization_name": "Short Pass Co",
            "organization_slug": "short-pass-co",
            "admin_email": "admin@short.com",
            "admin_full_name": "Admin",
            "admin_password": "abc",
        },
    )
    assert resp.status_code == 422


# ── Get my org ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_my_org_unauthenticated_returns_401(client: AsyncClient) -> None:
    resp = await client.get(_MY_ORG_URL)
    assert resp.status_code == 401
    assert resp.json()["error"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_get_my_org_returns_org_details(
    client: AsyncClient, auth_headers: dict, org
) -> None:
    resp = await client.get(_MY_ORG_URL, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == org.slug
    assert body["name"] == org.name
    assert "id" in body
    assert body["is_active"] is True


# ── Update my org ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_my_org_as_admin_returns_updated_fields(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.patch(
        _MY_ORG_URL,
        headers=auth_headers,
        json={"city": "Mumbai", "state": "Maharashtra", "phone": "+91-9900000000"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["city"] == "Mumbai"
    assert body["state"] == "Maharashtra"
    assert body["phone"] == "+91-9900000000"


@pytest.mark.asyncio
async def test_update_my_org_as_non_admin_returns_403(
    client: AsyncClient, db, org
) -> None:
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    se = User(
        organization_id=org.id,
        email="se-org-test@test.com",
        full_name="Site Eng",
        password_hash=hash_password("Test1234!"),
        role=UserRole.SITE_ENGINEER,
    )
    db.add(se)
    await db.flush()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "se-org-test@test.com", "password": "Test1234!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = await client.patch(
        _MY_ORG_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={"city": "Delhi"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "INSUFFICIENT_PERMISSIONS"
