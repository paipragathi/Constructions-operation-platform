"""
Custom exception hierarchy.

Design rules:
  1. Services raise domain exceptions — never HTTPException.
  2. Routers never catch exceptions — the global error handler does.
  3. Each exception carries enough context to form a useful error message.
  4. The HTTP status code is determined by the exception class, not by the
     caller. A NotFoundError is always 404.

Hierarchy:
    BaseAppException
    ├── NotFoundError                  → 404
    ├── ConflictError                  → 409
    ├── BusinessRuleViolationError     → 422
    ├── ValidationError                → 422
    ├── AuthenticationError            → 401
    ├── AuthorizationError             → 403
    └── InfrastructureError            → 503
"""


class BaseAppException(Exception):
    """Base for all application exceptions. Never raised directly."""

    default_message: str = "An unexpected error occurred"
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str | None = None, **context: object) -> None:
        self.message = message or self.default_message
        self.context = context  # extra fields logged alongside the exception
        super().__init__(self.message)


# ── 404 Not Found ──────────────────────────────────────────────────────────────

class NotFoundError(BaseAppException):
    default_message = "Resource not found"
    error_code = "NOT_FOUND"


class OrganizationNotFoundError(NotFoundError):
    default_message = "Organization not found"
    error_code = "ORGANIZATION_NOT_FOUND"


class UserNotFoundError(NotFoundError):
    default_message = "User not found"
    error_code = "USER_NOT_FOUND"


class ProjectNotFoundError(NotFoundError):
    default_message = "Project not found"
    error_code = "PROJECT_NOT_FOUND"


class SiteNotFoundError(NotFoundError):
    default_message = "Site not found"
    error_code = "SITE_NOT_FOUND"


class WorkerNotFoundError(NotFoundError):
    default_message = "Worker not found"
    error_code = "WORKER_NOT_FOUND"


class MaterialNotFoundError(NotFoundError):
    default_message = "Material not found"
    error_code = "MATERIAL_NOT_FOUND"


class IndentNotFoundError(NotFoundError):
    default_message = "Material indent not found"
    error_code = "INDENT_NOT_FOUND"


class PurchaseOrderNotFoundError(NotFoundError):
    default_message = "Purchase order not found"
    error_code = "PURCHASE_ORDER_NOT_FOUND"


class GrnNotFoundError(NotFoundError):
    default_message = "Goods receipt note not found"
    error_code = "GRN_NOT_FOUND"


class DocumentNotFoundError(NotFoundError):
    default_message = "Document not found"
    error_code = "DOCUMENT_NOT_FOUND"


class BackgroundTaskNotFoundError(NotFoundError):
    default_message = "Background task not found"
    error_code = "TASK_NOT_FOUND"


# ── 409 Conflict ───────────────────────────────────────────────────────────────

class ConflictError(BaseAppException):
    default_message = "Resource conflict"
    error_code = "CONFLICT"


class DuplicateEmailError(ConflictError):
    default_message = "An account with this email already exists"
    error_code = "DUPLICATE_EMAIL"


class DuplicateOrganizationError(ConflictError):
    default_message = "An organization with this name or slug already exists"
    error_code = "DUPLICATE_ORGANIZATION"


class AttendanceAlreadyMarkedError(ConflictError):
    default_message = "Attendance already marked for this worker on this date"
    error_code = "ATTENDANCE_ALREADY_MARKED"


# ── 422 Validation & Business Rule Violations ─────────────────────────────────

class AppValidationError(BaseAppException):
    """Domain-level input validation failure (distinct from Pydantic's ValidationError)."""
    default_message = "Validation failed"
    error_code = "VALIDATION_ERROR"


# Alias kept for backward compatibility within error_handlers.py
ValidationError = AppValidationError


class BusinessRuleViolationError(BaseAppException):
    default_message = "Business rule violation"
    error_code = "BUSINESS_RULE_VIOLATION"


class InvalidStatusTransitionError(BusinessRuleViolationError):
    default_message = "Invalid status transition"
    error_code = "INVALID_STATUS_TRANSITION"


class SelfApprovalError(BusinessRuleViolationError):
    default_message = "You cannot approve a record you created"
    error_code = "SELF_APPROVAL_NOT_ALLOWED"


class InsufficientStockError(BusinessRuleViolationError):
    default_message = "Insufficient stock to fulfill this request"
    error_code = "INSUFFICIENT_STOCK"


class ProjectClosedError(BusinessRuleViolationError):
    default_message = "Operation not allowed on a closed project"
    error_code = "PROJECT_CLOSED"


class PayrollAlreadyProcessedError(BusinessRuleViolationError):
    default_message = "Payroll has already been processed for this period"
    error_code = "PAYROLL_ALREADY_PROCESSED"


class ExceedsPurchaseOrderQuantityError(BusinessRuleViolationError):
    default_message = "Received quantity exceeds purchase order quantity"
    error_code = "EXCEEDS_PO_QUANTITY"


# ── 401 Authentication ─────────────────────────────────────────────────────────

class AuthenticationError(BaseAppException):
    default_message = "Authentication required"
    error_code = "AUTHENTICATION_REQUIRED"


class InvalidCredentialsError(AuthenticationError):
    default_message = "Invalid email or password"
    error_code = "INVALID_CREDENTIALS"


class TokenExpiredError(AuthenticationError):
    default_message = "Authentication token has expired"
    error_code = "TOKEN_EXPIRED"


class TokenInvalidError(AuthenticationError):
    default_message = "Authentication token is invalid"
    error_code = "TOKEN_INVALID"


class RefreshTokenRevokedError(AuthenticationError):
    default_message = "Refresh token has been revoked"
    error_code = "REFRESH_TOKEN_REVOKED"


# ── 403 Authorization ──────────────────────────────────────────────────────────

class AuthorizationError(BaseAppException):
    default_message = "You do not have permission to perform this action"
    error_code = "FORBIDDEN"


class InsufficientPermissionsError(AuthorizationError):
    default_message = "Your role does not have permission for this action"
    error_code = "INSUFFICIENT_PERMISSIONS"


class SiteAccessDeniedError(AuthorizationError):
    default_message = "You do not have access to this site"
    error_code = "SITE_ACCESS_DENIED"


class OrganizationAccessDeniedError(AuthorizationError):
    default_message = "You do not have access to this organization"
    error_code = "ORGANIZATION_ACCESS_DENIED"


# ── 503 Infrastructure ─────────────────────────────────────────────────────────

class InfrastructureError(BaseAppException):
    default_message = "A downstream service is unavailable"
    error_code = "SERVICE_UNAVAILABLE"


class DatabaseUnavailableError(InfrastructureError):
    default_message = "Database is unavailable"
    error_code = "DATABASE_UNAVAILABLE"


class RedisUnavailableError(InfrastructureError):
    default_message = "Cache service is unavailable"
    error_code = "CACHE_UNAVAILABLE"


class StorageUnavailableError(InfrastructureError):
    default_message = "Object storage is unavailable"
    error_code = "STORAGE_UNAVAILABLE"


class OcrServiceError(InfrastructureError):
    default_message = "OCR processing failed"
    error_code = "OCR_FAILED"
