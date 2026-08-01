"""
Integration tests for the authentication endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient, admin_user) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "wrong"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "AUTHENTICATION_REQUIRED"
    assert "request_id" in body


@pytest.mark.asyncio
async def test_login_invalid_email_format_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "whatever"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert body["details"][0]["field"] == "email"


@pytest.mark.asyncio
async def test_login_success_returns_tokens(client: AsyncClient, admin_user) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "Test1234!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_me_with_valid_token_returns_user(client: AsyncClient, admin_user) -> None:
    # Login first
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "Test1234!"},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    # Hit /me
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["email"] == "admin@test.com"
    assert body["role"] == "admin"


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient, admin_user) -> None:
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "Test1234!"},
    )
    assert login_resp.status_code == 200
    old_refresh = login_resp.json()["refresh_token"]

    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refresh_resp.status_code == 200
    body = refresh_resp.json()
    assert "access_token" in body
    # New refresh token must differ from old one (rotation)
    assert body["refresh_token"] != old_refresh


@pytest.mark.asyncio
async def test_logout_invalidates_refresh_token(client: AsyncClient, admin_user) -> None:
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "Test1234!"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 200

    # Token should no longer work
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 401
