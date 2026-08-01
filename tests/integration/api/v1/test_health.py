"""
Integration tests for health check endpoints.
These don't require authentication.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert "environment" in body


@pytest.mark.asyncio
async def test_readiness_returns_ok_when_db_healthy(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
