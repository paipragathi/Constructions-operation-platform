"""
Integration tests for worker document endpoints.

Covers: add, list, get, update, verify, delete, cross-tenant isolation,
verification idempotency guard, role enforcement on verify.
"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

_WORKERS_URL = "/api/v1/workers"
_DOCS_URL = "/api/v1/worker-documents"


@pytest_asyncio.fixture
async def worker(client: AsyncClient, auth_headers: dict) -> dict:
    resp = await client.post(
        _WORKERS_URL,
        headers=auth_headers,
        json={"employee_code": "DOC-W001", "full_name": "Doc Worker", "trade": "electrician"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def document(client: AsyncClient, auth_headers: dict, worker: dict) -> dict:
    resp = await client.post(
        f"{_WORKERS_URL}/{worker['id']}/documents",
        headers=auth_headers,
        json={
            "document_type": "aadhaar",
            "document_number": "1234-5678-9012",
            "notes": "Original Aadhaar",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── POST /workers/{id}/documents ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_document_returns_201(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.post(
        f"{_WORKERS_URL}/{worker['id']}/documents",
        headers=auth_headers,
        json={"document_type": "pan", "document_number": "ABCDE1234F"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["document_type"] == "pan"
    assert body["document_number"] == "ABCDE1234F"
    assert body["verified"] is False
    assert body["file_key"] is None  # placeholder until Sprint 6


@pytest.mark.asyncio
async def test_add_document_with_file_key_placeholder(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.post(
        f"{_WORKERS_URL}/{worker['id']}/documents",
        headers=auth_headers,
        json={
            "document_type": "photo",
            "file_key": "workers/photos/abc123.jpg",
            "file_name": "photo.jpg",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["file_key"] == "workers/photos/abc123.jpg"


@pytest.mark.asyncio
async def test_add_document_invalid_type_returns_422(
    client: AsyncClient, auth_headers: dict, worker: dict
) -> None:
    resp = await client.post(
        f"{_WORKERS_URL}/{worker['id']}/documents",
        headers=auth_headers,
        json={"document_type": "passport"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_add_document_to_nonexistent_worker_returns_404(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.post(
        f"{_WORKERS_URL}/00000000-0000-0000-0000-000000000088/documents",
        headers=auth_headers,
        json={"document_type": "aadhaar"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_document_unauthenticated_returns_401(
    client: AsyncClient, worker: dict
) -> None:
    resp = await client.post(
        f"{_WORKERS_URL}/{worker['id']}/documents",
        json={"document_type": "aadhaar"},
    )
    assert resp.status_code == 401


# ── GET /workers/{id}/documents ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_documents_returns_paginated(
    client: AsyncClient, auth_headers: dict, worker: dict, document: dict
) -> None:
    resp = await client.get(
        f"{_WORKERS_URL}/{worker['id']}/documents", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 1
    doc_types = [d["document_type"] for d in body["items"]]
    assert "aadhaar" in doc_types


# ── GET /worker-documents/{id} ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_document_returns_200(
    client: AsyncClient, auth_headers: dict, document: dict
) -> None:
    resp = await client.get(f"{_DOCS_URL}/{document['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == document["id"]


@pytest.mark.asyncio
async def test_get_document_cross_tenant_returns_404(
    client: AsyncClient, auth_headers: dict, document: dict
) -> None:
    reg = await client.post(
        "/api/v1/organizations",
        json={
            "organization_name": "Outsider Corp",
            "organization_slug": "outsider-corp",
            "admin_email": "outsider@corp.com",
            "admin_full_name": "Outsider Admin",
            "admin_password": "SecurePass1!",
        },
    )
    assert reg.status_code == 201
    token_out = reg.json()["access_token"]

    resp = await client.get(
        f"{_DOCS_URL}/{document['id']}",
        headers={"Authorization": f"Bearer {token_out}"},
    )
    assert resp.status_code == 404


# ── PATCH /worker-documents/{id} ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_document_notes_returns_200(
    client: AsyncClient, auth_headers: dict, document: dict
) -> None:
    resp = await client.patch(
        f"{_DOCS_URL}/{document['id']}",
        headers=auth_headers,
        json={"notes": "Verified physical copy on 2026-08-01"},
    )
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Verified physical copy on 2026-08-01"


@pytest.mark.asyncio
async def test_update_document_file_key(
    client: AsyncClient, auth_headers: dict, document: dict
) -> None:
    resp = await client.patch(
        f"{_DOCS_URL}/{document['id']}",
        headers=auth_headers,
        json={"file_key": "workers/aadhaar/xyz.pdf", "file_name": "aadhaar.pdf"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["file_key"] == "workers/aadhaar/xyz.pdf"
    assert body["file_name"] == "aadhaar.pdf"


# ── POST /worker-documents/{id}/verify ────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_document_as_admin_returns_200(
    client: AsyncClient, auth_headers: dict, document: dict
) -> None:
    resp = await client.post(
        f"{_DOCS_URL}/{document['id']}/verify", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["verified_by"] is not None
    assert body["verified_at"] is not None


@pytest.mark.asyncio
async def test_verify_already_verified_document_returns_422(
    client: AsyncClient, auth_headers: dict, document: dict
) -> None:
    await client.post(f"{_DOCS_URL}/{document['id']}/verify", headers=auth_headers)
    resp = await client.post(f"{_DOCS_URL}/{document['id']}/verify", headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["error"] == "BUSINESS_RULE_VIOLATION"


@pytest.mark.asyncio
async def test_verify_document_as_site_engineer_returns_403(
    client: AsyncClient, db, org, document: dict
) -> None:
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    se = User(
        organization_id=org.id,
        email="se-verify@test.com",
        full_name="SE Verify",
        password_hash=hash_password("Test1234!"),
        role=UserRole.SITE_ENGINEER,
    )
    db.add(se)
    await db.flush()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "se-verify@test.com", "password": "Test1234!"},
    )
    token = login.json()["access_token"]

    resp = await client.post(
        f"{_DOCS_URL}/{document['id']}/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── DELETE /worker-documents/{id} ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_document_returns_200(
    client: AsyncClient, auth_headers: dict, document: dict
) -> None:
    resp = await client.delete(f"{_DOCS_URL}/{document['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_get_deleted_document_returns_404(
    client: AsyncClient, auth_headers: dict, document: dict
) -> None:
    await client.delete(f"{_DOCS_URL}/{document['id']}", headers=auth_headers)
    resp = await client.get(f"{_DOCS_URL}/{document['id']}", headers=auth_headers)
    assert resp.status_code == 404
