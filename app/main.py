"""
FastAPI application factory.

Import this module from any entrypoint:
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.database import engine
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import AccessLogMiddleware, RequestIDMiddleware

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log.info(
        "startup",
        app=settings.app_name,
        environment=settings.environment,
    )
    yield
    await engine.dispose()
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Construction Site Operations Platform API",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost runs first on request, last on response)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # ── Exception handlers
    register_exception_handlers(app)

    # ── Routers
    app.include_router(health_router)             # /health, /health/ready
    app.include_router(v1_router, prefix=settings.api_prefix)  # /api/v1/...

    # ── Prometheus metrics
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/health/ready", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    return app


app = create_app()
