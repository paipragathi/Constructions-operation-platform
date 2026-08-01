"""
Health-check endpoints.

GET /health       — liveness probe (always returns 200 if process is alive)
GET /health/ready — readiness probe (checks DB connectivity)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import check_database_connection, get_db
from app.schemas.common import HealthResponse
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, include_in_schema=False)
async def liveness() -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        database=True,  # if we got here, the process is alive
    )


@router.get("/health/ready", response_model=HealthResponse, include_in_schema=False)
async def readiness(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    db_ok = await check_database_connection()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        environment=settings.environment,
        database=db_ok,
    )
