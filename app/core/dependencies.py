"""
Shared FastAPI dependencies.

These are injected into route handlers via Depends().
They form the authentication and authorization chain.

Dependency chain:
    get_db                → provides AsyncSession to repositories
    get_current_user      → decodes JWT, loads user from DB/cache
    require_role(...)     → wraps get_current_user, checks role
    require_permission(.) → wraps get_current_user, checks permission

Usage in a router:
    @router.post("/indents/{id}/approve")
    async def approve_indent(
        indent_id: UUID,
        db: AsyncSession = Depends(get_db),
        current_user: UserInToken = Depends(require_role("project_manager", "admin")),
    ):
        ...
"""

from dataclasses import dataclass
from uuid import UUID

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import (
    AuthenticationError,
    InsufficientPermissionsError,
    TokenInvalidError,
)
from app.core.security import decode_access_token

logger = structlog.get_logger(__name__)

# HTTPBearer extracts the Bearer token from the Authorization header.
# auto_error=False means we handle the 401 ourselves with our error envelope.
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class UserInToken:
    """
    The authenticated user extracted from a verified JWT.
    Immutable dataclass — created once per request, passed through DI.

    Only identity and role are here — site assignments and project access
    are fetched from DB/cache when needed, not embedded in the token.
    """

    user_id: UUID
    role: str
    organization_id: UUID


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),  # noqa: ARG001 — available for future DB lookups
) -> UserInToken:
    """
    Decode and verify the JWT. Return a UserInToken.

    Raises:
      AuthenticationError  → no token, expired token, invalid signature
    """
    if credentials is None:
        raise AuthenticationError("Authorization header is missing or malformed")

    payload = decode_access_token(credentials.credentials)

    try:
        user_id = UUID(str(payload["sub"]))
        organization_id = UUID(str(payload["org"]))
        role = str(payload["role"])
    except (KeyError, ValueError) as e:
        raise TokenInvalidError(f"Token payload is malformed: {e}")

    # Bind identity to structlog context — appears on all log lines after this
    structlog.contextvars.bind_contextvars(
        user_id=str(user_id),
        organization_id=str(organization_id),
        role=role,
    )

    return UserInToken(user_id=user_id, role=role, organization_id=organization_id)


def require_role(*allowed_roles: str):
    """
    Dependency factory that checks the current user's role.

    Returns a dependency function that calls get_current_user and raises
    InsufficientPermissionsError if the user's role is not in allowed_roles.

    Usage:
        current_user = Depends(require_role("project_manager", "admin"))
    """

    async def _check_role(
        current_user: UserInToken = Depends(get_current_user),
    ) -> UserInToken:
        if current_user.role not in allowed_roles and current_user.role != "admin":
            logger.warning(
                "authorization.role_check_failed",
                required_roles=allowed_roles,
                user_role=current_user.role,
            )
            raise InsufficientPermissionsError(
                f"This action requires one of: {', '.join(allowed_roles)}"
            )
        return current_user

    return _check_role


# ── Re-export get_db so other modules import from one place ───────────────────
__all__ = ["get_db", "get_current_user", "require_role", "UserInToken"]
