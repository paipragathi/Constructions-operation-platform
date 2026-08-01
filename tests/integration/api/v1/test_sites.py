"""
Integration tests for site endpoints.

Covers: CRUD under project, closed-project guard, cross-tenant isolation.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

_PROJECTS_URL = "/api/v1/projects"
_SITES_URL = "/api/v1/sites"


@pytest_asyncio.fixture
async def active_project(client: AsyncClient, auth_headers: dict) -> dict:
    """Create a project and transition it to active."""
    create = await client.post(
        _PROJECTS_URL,
        headers=auth_headers,
        json={"name": "Active Site Project", "code": "SITE-001"},
    )
    assert create.status_code == 201
    pid = create.json()["id"]

    transition = await client.post(
        f"{_PROJECTS_URL}/{pid}/status",
        headers=auth_headers,
        json={"status": "active"},
    )
    assert transition.status_code == 200
    return transition.json()


@pytest_asyncio.fixture
async def site(client: AsyncClient, auth_headers: dict, active_project: dict) -> dict:
    """Create a site under the active project and return its response body."""
    resp = await client.post(
        f"{_PROJECTS_URL}/{active_project['id']}/sites",
        headers=auth_headers,
        json={
            "name": "Main Site",
            "city": "Hyderabad",
            "state": "Telangana",
            "pincode": "500032",
        },
    )
    assert resp.status_code == 201
    return resp.json()


# ── POST /projects/{id}/sites ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_site_returns_201(
    client: AsyncClient, auth_headers: dict, active_project: dict
) -> None:
    resp = await client.post(
        f"{_PROJECTS_URL}/{active_project['id']}/sites",
        headers=auth_headers,
        json={"name": "Block A Site", "city": "Pune", "state": "Maharashtra"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Block A Site"
    assert body["project_id"] == active_project["id"]
    assert body["is_deleted"] is False


@pytest.mark.asyncio
async def test_create_site_on_closed_project_returns_422(
    client: AsyncClient, auth_headers: dict, active_project: dict
) -> None:
    pid = active_project["id"]

    await client.post(
        f"{_PROJECTS_URL}/{pid}/status",
        headers=auth_headers,
        json={"status": "closed"},
    )

    resp = await client.post(
        f"{_PROJECTS_URL}/{pid}/sites",
        headers=auth_headers,
        json={"name": "Late Site"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "BUSINESS_RULE_VIOLATION"


@pytest.mark.asyncio
async def test_create_site_on_nonexistent_project_returns_404(
    client: AsyncClient, auth_headers: dict
) -> None:
    fake_pid = "00000000-0000-0000-0000-000000000003"
    resp = await client.post(
        f"{_PROJECTS_URL}/{fake_pid}/sites",
        headers=auth_headers,
        json={"name": "Ghost Site"},
    )
    assert resp.status_code == 404


# ── GET /projects/{id}/sites ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_sites_returns_paginated_response(
    client: AsyncClient, auth_headers: dict, active_project: dict, site: dict
) -> None:
    resp = await client.get(
        f"{_PROJECTS_URL}/{active_project['id']}/sites",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 1
    names = [s["name"] for s in body["items"]]
    assert site["name"] in names


# ── GET /sites/{id} ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_site_returns_200(
    client: AsyncClient, auth_headers: dict, site: dict
) -> None:
    resp = await client.get(f"{_SITES_URL}/{site['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == site["id"]


@pytest.mark.asyncio
async def test_get_site_cross_tenant_returns_404(
    client: AsyncClient, auth_headers: dict, site: dict
) -> None:
    """Org B cannot read Org A's site — base repo org_id filter → 404."""
    reg = await client.post(
        "/api/v1/organizations",
        json={
            "organization_name": "Tenant C Constructions",
            "organization_slug": "tenant-c-constructions",
            "admin_email": "adminc@constructions.com",
            "admin_full_name": "Admin C",
            "admin_password": "SecurePass1!",
        },
    )
    assert reg.status_code == 201
    token_c = reg.json()["access_token"]

    resp = await client.get(
        f"{_SITES_URL}/{site['id']}",
        headers={"Authorization": f"Bearer {token_c}"},
    )
    assert resp.status_code == 404


# ── PATCH /sites/{id} ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_site_returns_200_with_new_name(
    client: AsyncClient, auth_headers: dict, site: dict
) -> None:
    resp = await client.patch(
        f"{_SITES_URL}/{site['id']}",
        headers=auth_headers,
        json={"name": "Updated Site Name", "city": "Bengaluru"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Updated Site Name"
    assert body["city"] == "Bengaluru"


# ── DELETE /sites/{id} ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_site_returns_200(
    client: AsyncClient, auth_headers: dict, site: dict
) -> None:
    resp = await client.delete(f"{_SITES_URL}/{site['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_get_deleted_site_returns_404(
    client: AsyncClient, auth_headers: dict, site: dict
) -> None:
    await client.delete(f"{_SITES_URL}/{site['id']}", headers=auth_headers)
    resp = await client.get(f"{_SITES_URL}/{site['id']}", headers=auth_headers)
    assert resp.status_code == 404
