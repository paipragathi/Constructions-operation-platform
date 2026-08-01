"""
Global exception handlers.

Maps custom exception classes to HTTP responses with a consistent error envelope.
Registered on the FastAPI app in app/main.py.

Every error response has the shape:
    {
        "error":      "ERROR_CODE",
        "message":    "Human-readable description",
        "details":    null | [{"field": "...", "message": "..."}],
        "request_id": "req_abc123"
    }
"""

import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BaseAppException,
    BusinessRuleViolationError,
    ConflictError,
    InfrastructureError,
    NotFoundError,
    ValidationError,
)

logger = structlog.get_logger(__name__)


def _error_response(
    request: Request,
    status_code: int,
    error_code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> JSONResponse:
    """Build the standard error envelope."""
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id", "")
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error_code,
            "message": message,
            "details": details,
            "request_id": request_id,
        },
    )


# ── Domain exception handlers ──────────────────────────────────────────────────

async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    logger.info("request.not_found", error_code=exc.error_code, message=exc.message)
    return _error_response(request, status.HTTP_404_NOT_FOUND, exc.error_code, exc.message)


async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    logger.info("request.conflict", error_code=exc.error_code, message=exc.message)
    return _error_response(request, status.HTTP_409_CONFLICT, exc.error_code, exc.message)


async def business_rule_handler(
    request: Request, exc: BusinessRuleViolationError
) -> JSONResponse:
    logger.info("request.business_rule_violation", error_code=exc.error_code, message=exc.message)
    return _error_response(
        request, status.HTTP_422_UNPROCESSABLE_CONTENT, exc.error_code, exc.message
    )


async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    logger.info("request.validation_error", error_code=exc.error_code, message=exc.message)
    return _error_response(
        request, status.HTTP_422_UNPROCESSABLE_CONTENT, exc.error_code, exc.message
    )


async def authentication_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    logger.info("request.authentication_failed", error_code=exc.error_code)
    return _error_response(
        request, status.HTTP_401_UNAUTHORIZED, exc.error_code, exc.message
    )


async def authorization_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    logger.info("request.authorization_failed", error_code=exc.error_code)
    return _error_response(
        request, status.HTTP_403_FORBIDDEN, exc.error_code, exc.message
    )


async def infrastructure_handler(request: Request, exc: InfrastructureError) -> JSONResponse:
    logger.error("request.infrastructure_error", error_code=exc.error_code, error=str(exc))
    return _error_response(
        request, status.HTTP_503_SERVICE_UNAVAILABLE, exc.error_code, exc.message
    )


# ── Pydantic validation errors (FastAPI's 422) ─────────────────────────────────

async def pydantic_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Converts FastAPI's default Pydantic validation errors to our standard envelope.
    Extracts field-level error details for the client.
    """
    details = [
        {
            "field": ".".join(str(loc) for loc in error["loc"] if loc != "body"),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    logger.info("request.validation_error.pydantic", detail_count=len(details))
    return _error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "VALIDATION_ERROR",
        "Input validation failed",
        details=details,
    )


# ── Starlette HTTP exceptions (404 from route not found, etc.) ─────────────────

async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return _error_response(
        request,
        exc.status_code,
        "HTTP_ERROR",
        str(exc.detail),
    )


# ── Catch-all: unhandled exceptions ───────────────────────────────────────────

async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Safety net for any exception that escaped all other handlers.
    Logs the full traceback. Never exposes internal details to the caller.
    """
    logger.error(
        "request.unhandled_exception",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        exc_info=True,
    )
    return _error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        "An unexpected error occurred. Please try again or contact support.",
    )


def register_exception_handlers(app: "fastapi.FastAPI") -> None:  # type: ignore[name-defined]
    """Register all exception handlers on the FastAPI app. Called from main.py."""
    import fastapi

    app.add_exception_handler(NotFoundError, not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ConflictError, conflict_handler)  # type: ignore[arg-type]
    app.add_exception_handler(BusinessRuleViolationError, business_rule_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AuthenticationError, authentication_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AuthorizationError, authorization_handler)  # type: ignore[arg-type]
    app.add_exception_handler(InfrastructureError, infrastructure_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, pydantic_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
