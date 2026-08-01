"""
Integration tests for project endpoints.

Covers: CRUD, status machine transitions, deletion guards, cross-tenant isolation.
"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

_PROJECTS_URL = "/api/v1/projects"

_PROJECT_PAYLOAD = {
    "name": "Hyderabad Heights",
    "code": "HYD-001",
    "description": "Residential project",
    "budget": "15000000.00",
}


@pytest_asyncio.fixture
async def project(client: AsyncClient, auth_headers: dict) -> dict:
    """Create a draft project and return its response body."""
    resp = await client.post(_PROJECTS_URL, headers=auth_headers, json=_PROJECT_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()


# ── POST /projects ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_project_returns_201_with_draft_status(
    client: AsyncClient, auth_headers: dict, admin_user
) -> None:
    resp = await client.post(
        _PROJECTS_URL,
        headers=auth_headers,
        json={"name": "Chennai Complex", "code": "CHN-001"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "draft"
    assert body["code"] == "CHN-001"
    assert body["is_deleted"] is False


@pytest.mark.asyncio
async def test_create_project_code_is_uppercased(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.post(
        _PROJECTS_URL,
        headers=auth_headers,
        json={"name": "Lower Code Project", "code": "lower-abc"},
    )
    assert resp.status_code == 201
    assert resp.json()["code"] == "LOWER-ABC"


@pytest.mark.asyncio
async def test_create_project_duplicate_code_returns_409(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    resp = await client.post(
        _PROJECTS_URL,
        headers=auth_headers,
        json={"name": "Different Name", "code": project["code"]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "CONFLICT"


@pytest.mark.asyncio
async def test_create_project_as_non_write_role_returns_403(
    client: AsyncClient, db, org
) -> None:
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    se = User(
        organization_id=org.id,
        email="se-proj@test.com",
        full_name="Site Eng",
        password_hash=hash_password("Test1234!"),
        role=UserRole.SITE_ENGINEER,
    )
    db.add(se)
    await db.flush()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "se-proj@test.com", "password": "Test1234!"},
    )
    token = login.json()["access_token"]

    resp = await client.post(
        _PROJECTS_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Unauthorized", "code": "UNAUTH-001"},
    )
    assert resp.status_code == 403


# ── GET /projects ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_projects_returns_paginated_response(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    resp = await client.get(_PROJECTS_URL, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 1
    codes = [p["code"] for p in body["items"]]
    assert project["code"] in codes


@pytest.mark.asyncio
async def test_list_projects_filter_by_status(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    resp = await client.get(
        _PROJECTS_URL, headers=auth_headers, params={"status": "draft"}
    )
    assert resp.status_code == 200
    for p in resp.json()["items"]:
        assert p["status"] == "draft"


# ── GET /projects/{id} ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_project_by_id_returns_200(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    resp = await client.get(f"{_PROJECTS_URL}/{project['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == project["id"]


@pytest.mark.asyncio
async def test_get_project_cross_tenant_returns_404(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    """Org B cannot see Org A's project — base repo filters on org_id → 404."""
    reg = await client.post(
        "/api/v1/organizations",
        json={
            "organization_name": "Tenant B Builders",
            "organization_slug": "tenant-b-builders",
            "admin_email": "adminb@builders.com",
            "admin_full_name": "Admin B",
            "admin_password": "SecurePass1!",
        },
    )
    assert reg.status_code == 201
    token_b = reg.json()["access_token"]

    resp = await client.get(
        f"{_PROJECTS_URL}/{project['id']}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404


# ── PATCH /projects/{id} ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_project_returns_200_with_new_name(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    resp = await client.patch(
        f"{_PROJECTS_URL}/{project['id']}",
        headers=auth_headers,
        json={"name": "Updated Project Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Project Name"


# ── POST /projects/{id}/status ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_transition_draft_to_active_returns_200(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    resp = await client.post(
        f"{_PROJECTS_URL}/{project['id']}/status",
        headers=auth_headers,
        json={"status": "active"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_transition_active_to_closed_sets_actual_end_date(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    # draft → active
    await client.post(
        f"{_PROJECTS_URL}/{project['id']}/status",
        headers=auth_headers,
        json={"status": "active"},
    )
    # active → closed
    resp = await client.post(
        f"{_PROJECTS_URL}/{project['id']}/status",
        headers=auth_headers,
        json={"status": "closed"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "closed"
    assert body["actual_end_date"] is not None


@pytest.mark.asyncio
async def test_transition_active_to_on_hold_and_back(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    pid = project["id"]
    await client.post(f"{_PROJECTS_URL}/{pid}/status", headers=auth_headers, json={"status": "active"})
    await client.post(f"{_PROJECTS_URL}/{pid}/status", headers=auth_headers, json={"status": "on_hold"})
    resp = await client.post(f"{_PROJECTS_URL}/{pid}/status", headers=auth_headers, json={"status": "active"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_invalid_transition_draft_to_closed_returns_422(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    resp = await client.post(
        f"{_PROJECTS_URL}/{project['id']}/status",
        headers=auth_headers,
        json={"status": "closed"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_STATUS_TRANSITION"


@pytest.mark.asyncio
async def test_invalid_transition_closed_to_active_returns_422(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    pid = project["id"]
    await client.post(f"{_PROJECTS_URL}/{pid}/status", headers=auth_headers, json={"status": "active"})
    await client.post(f"{_PROJECTS_URL}/{pid}/status", headers=auth_headers, json={"status": "closed"})

    resp = await client.post(
        f"{_PROJECTS_URL}/{pid}/status",
        headers=auth_headers,
        json={"status": "active"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_STATUS_TRANSITION"


# ── DELETE /projects/{id} ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_draft_project_returns_200(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    resp = await client.delete(
        f"{_PROJECTS_URL}/{project['id']}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_delete_active_project_returns_422(
    client: AsyncClient, auth_headers: dict, project: dict
) -> None:
    pid = project["id"]
    await client.post(f"{_PROJECTS_URL}/{pid}/status", headers=auth_headers, json={"status": "active"})

    resp = await client.delete(f"{_PROJECTS_URL}/{pid}", headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["error"] == "BUSINESS_RULE_VIOLATION"
