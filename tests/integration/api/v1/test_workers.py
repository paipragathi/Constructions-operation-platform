"""
Integration tests for worker endpoints.

Covers: CRUD, employee_code uniqueness, trade/skill validation,
role enforcement, cross-tenant isolation.
"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

_WORKERS_URL = "/api/v1/workers"

_WORKER_PAYLOAD = {
    "employee_code": "W-001",
    "full_name": "Ramesh Kumar",
    "trade": "mason",
    "skill_level": "skilled",
    "phone": "+91-9000000001",
    "daily_wage_rate": "750.00",
}


@pytest_asyncio.fixture
async def worker(client: AsyncClient, auth_headers: dict) -> dict:
    """Create a worker and return its response body."""
    resp = await client.post(_WORKERS_URL, headers=auth_headers, json=_WORKER_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── POST /workers ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_worker_returns_201(
    client: AsyncClient, auth_headers: dict, admin_user
) -> None:
    resp = await client.post(
        _WORKERS_URL,
        headers=auth_headers,
        json={"employee_code": "W-010", "full_name": "Suresh Yadav", "trade": "carpenter"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["employee_code"] == "W-010"
    assert body["trade"] == "carpenter"
    assert body["skill_level"] == "unskilled"  # default
    assert body["is_active"] is True
    assert body["is_deleted"] is False


@pytest.mark.asyncio
async def test_create_worker_code_is_uppercased(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.post(
        _WORKERS_URL,
        headers=auth_headers,
        json={"employee_code": "w-099", "full_name": "Lower Code", "trade": "helper"},
    )
    assert resp.status_code == 201
    assert resp.json()["employee_code"] == "W-099"


@pytest.mark.asyncio
async def test_create_worker_duplicate_code_returns_409(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.post(
        _WORKERS_URL,
        headers=auth_headers,
        json={"employee_code": worker["employee_code"], "full_name": "Other Worker", "trade": "plumber"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "CONFLICT"


@pytest.mark.asyncio
async def test_create_worker_invalid_trade_returns_422(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.post(
        _WORKERS_URL,
        headers=auth_headers,
        json={"employee_code": "W-BAD", "full_name": "Bad Trade", "trade": "astronaut"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_worker_invalid_skill_level_returns_422(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.post(
        _WORKERS_URL,
        headers=auth_headers,
        json={
            "employee_code": "W-BAD2",
            "full_name": "Bad Skill",
            "trade": "mason",
            "skill_level": "expert",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_worker_as_watchman_returns_403(
    client: AsyncClient, db, org
) -> None:
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    watchman = User(
        organization_id=org.id,
        email="watchman@test.com",
        full_name="Watchman",
        password_hash=hash_password("Test1234!"),
        role=UserRole.ACCOUNTS,
    )
    db.add(watchman)
    await db.flush()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "watchman@test.com", "password": "Test1234!"},
    )
    token = login.json()["access_token"]

    resp = await client.post(
        _WORKERS_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={"employee_code": "W-FAIL", "full_name": "Fail", "trade": "helper"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_worker_unauthenticated_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        _WORKERS_URL,
        json={"employee_code": "W-002", "full_name": "Ghost", "trade": "helper"},
    )
    assert resp.status_code == 401


# ── GET /workers ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_workers_returns_paginated(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.get(_WORKERS_URL, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 1
    codes = [w["employee_code"] for w in body["items"]]
    assert worker["employee_code"] in codes


@pytest.mark.asyncio
async def test_list_workers_filter_by_trade(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.get(_WORKERS_URL, headers=auth_headers, params={"trade": "mason"})
    assert resp.status_code == 200
    for w in resp.json()["items"]:
        assert w["trade"] == "mason"


@pytest.mark.asyncio
async def test_list_workers_filter_by_active(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.get(_WORKERS_URL, headers=auth_headers, params={"is_active": True})
    assert resp.status_code == 200
    for w in resp.json()["items"]:
        assert w["is_active"] is True


@pytest.mark.asyncio
async def test_list_workers_invalid_trade_filter_returns_422(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.get(_WORKERS_URL, headers=auth_headers, params={"trade": "alien"})
    assert resp.status_code == 422


# ── GET /workers/{id} ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_worker_returns_200(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.get(f"{_WORKERS_URL}/{worker['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == worker["id"]
    assert resp.json()["full_name"] == worker["full_name"]


@pytest.mark.asyncio
async def test_get_nonexistent_worker_returns_404(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.get(
        f"{_WORKERS_URL}/00000000-0000-0000-0000-000000000099",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_worker_cross_tenant_returns_404(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    reg = await client.post(
        "/api/v1/organizations",
        json={
            "organization_name": "Rival Builders",
            "organization_slug": "rival-builders",
            "admin_email": "rival@builders.com",
            "admin_full_name": "Rival Admin",
            "admin_password": "SecurePass1!",
        },
    )
    assert reg.status_code == 201
    rival_token = reg.json()["access_token"]

    resp = await client.get(
        f"{_WORKERS_URL}/{worker['id']}",
        headers={"Authorization": f"Bearer {rival_token}"},
    )
    assert resp.status_code == 404


# ── PATCH /workers/{id} ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_worker_returns_200(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.patch(
        f"{_WORKERS_URL}/{worker['id']}",
        headers=auth_headers,
        json={"full_name": "Ramesh Kumar Updated", "skill_level": "highly_skilled"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "Ramesh Kumar Updated"
    assert body["skill_level"] == "highly_skilled"


@pytest.mark.asyncio
async def test_update_worker_deactivate(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.patch(
        f"{_WORKERS_URL}/{worker['id']}",
        headers=auth_headers,
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# ── DELETE /workers/{id} ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_worker_returns_200(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.delete(
        f"{_WORKERS_URL}/{worker['id']}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_get_deleted_worker_returns_404(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    await client.delete(f"{_WORKERS_URL}/{worker['id']}", headers=auth_headers)
    resp = await client.get(f"{_WORKERS_URL}/{worker['id']}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_worker_as_non_admin_returns_403(
    client: AsyncClient, db, org, worker: dict
) -> None:
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    se = User(
        organization_id=org.id,
        email="se-del@test.com",
        full_name="Site Eng",
        password_hash=hash_password("Test1234!"),
        role=UserRole.SITE_ENGINEER,
    )
    db.add(se)
    await db.flush()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "se-del@test.com", "password": "Test1234!"},
    )
    token = login.json()["access_token"]

    resp = await client.delete(
        f"{_WORKERS_URL}/{worker['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
