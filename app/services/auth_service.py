"""
Authentication service.

Responsibilities:
- Login: verify credentials, issue access + refresh tokens
- Refresh: rotate refresh token (old one deleted, new one issued)
- Logout: revoke refresh token
- Me: return current user info from DB

Rules:
- Never raises HTTPException — only domain exceptions from app.core.exceptions
- Never touches HTTP layer (no Request, Response objects)
- Token rotation on every refresh (prevents replay attacks)
"""

import hashlib
import structlog
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, NotFoundError
from app.core.metrics import AUTH_LOGIN_ATTEMPTS, AUTH_TOKEN_REFRESH
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.schemas.auth import TokenResponse, UserMeResponse
from app.core.config import settings

log = structlog.get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)

    async def login(
        self,
        email: str,
        password: str,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenResponse:
        user = await self._users.get_active_by_email(email)

        # Verify password regardless of whether user exists — prevents timing attacks
        password_ok = verify_password(password, user.password_hash) if user else False

        if not user or not password_ok:
            AUTH_LOGIN_ATTEMPTS.labels(status="failure").inc()
            log.warning("login_failed", email=email)
            raise AuthenticationError("Invalid email or password")

        AUTH_LOGIN_ATTEMPTS.labels(status="success").inc()

        raw_token = generate_refresh_token()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        refresh = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=refresh_token_expiry(),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self._tokens.create(refresh)
        await self._users.update_last_login(user.id)

        access_token = create_access_token(
            user_id=str(user.id),
            role=user.role,
            organization_id=str(user.organization_id),
        )

        log.info("login_success", user_id=str(user.id), role=user.role)
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_token,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def refresh(self, raw_token: str) -> TokenResponse:
        stored = await self._tokens.get_by_token(raw_token)

        if not stored:
            AUTH_TOKEN_REFRESH.labels(status="not_found").inc()
            raise AuthenticationError("Refresh token not found or already used")

        if stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            AUTH_TOKEN_REFRESH.labels(status="expired").inc()
            await self._tokens.delete_by_token(raw_token)
            raise AuthenticationError("Refresh token expired — please log in again")

        user = await self._session.get(User, stored.user_id)
        if not user or not user.is_active:
            AUTH_TOKEN_REFRESH.labels(status="user_inactive").inc()
            raise AuthenticationError("Account is inactive")

        # Token rotation: delete old, issue new
        await self._tokens.delete_by_token(raw_token)

        new_raw = generate_refresh_token()
        new_hash = hashlib.sha256(new_raw.encode()).hexdigest()
        new_token = RefreshToken(
            user_id=user.id,
            token_hash=new_hash,
            expires_at=refresh_token_expiry(),
            user_agent=stored.user_agent,
            ip_address=stored.ip_address,
        )
        await self._tokens.create(new_token)

        access_token = create_access_token(
            user_id=str(user.id),
            role=user.role,
            organization_id=str(user.organization_id),
        )

        AUTH_TOKEN_REFRESH.labels(status="success").inc()
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_raw,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def logout(self, raw_token: str) -> None:
        await self._tokens.delete_by_token(raw_token)
        log.info("logout")

    async def logout_all_devices(self, user_id_str: str) -> None:
        """Revoke every session for this user."""
        from uuid import UUID
        await self._tokens.delete_all_for_user(UUID(user_id_str))
        log.info("logout_all_devices", user_id=user_id_str)

    async def get_me(self, user_id_str: str) -> UserMeResponse:
        from uuid import UUID
        user = await self._session.get(User, UUID(user_id_str))
        if not user or user.is_deleted:
            raise NotFoundError(resource="user", identifier=user_id_str)
        return UserMeResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            organization_id=str(user.organization_id),
            is_active=user.is_active,
        )
