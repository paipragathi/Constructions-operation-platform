"""
Request middleware.

RequestIDMiddleware:
  Generates (or propagates) a unique request ID for every request.
  Binds it to the structlog context so every log line within the request
  automatically carries the request_id field.
  Returns the request_id in the X-Request-ID response header.

AccessLogMiddleware:
  Logs one line per request: method, path, status_code, duration_ms.
  This is the minimal observability baseline — you can see which endpoints
  are slow and which return errors without setting up Prometheus yet.
"""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Attaches a unique request ID to every request.

    Priority:
      1. Use X-Request-ID header if the client sent one (useful when the caller
         is another service that generated the ID upstream).
      2. Generate a new UUID4 otherwise.

    The ID is:
      - Bound to structlog context (appears on every log line in this request)
      - Returned in X-Request-ID response header (so clients can correlate)
      - Included in every error response body
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"

        # Store on request state so handlers can access it
        request.state.request_id = request_id

        # Bind to structlog context — automatically appears on all log lines
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    Logs one structured line per completed request.

    Logged fields: method, path, status_code, duration_ms, request_id.
    After authentication middleware runs, also: user_id, organization_id.

    Skip logging for:
      - /health (too noisy, called every 15 seconds by Prometheus/load balancer)
      - /metrics (Prometheus scrape, not a real user request)
    """

    SKIP_PATHS = {"/health", "/health/ready", "/metrics"}

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        log_method = logger.warning if response.status_code >= 400 else logger.info

        log_method(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=request.client.host if request.client else None,
        )

        return response
