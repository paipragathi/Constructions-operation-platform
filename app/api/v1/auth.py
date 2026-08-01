"""
Authentication API.

POST /auth/login          — issue access + refresh tokens
POST /auth/refresh        — rotate refresh token, issue new access token
POST /auth/logout         — revoke current refresh token
POST /auth/logout-all     — revoke all sessions (password change, compromise)
GET  /auth/me             — current user profile
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import UserInToken, get_current_user
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
    UserMeResponse,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])


def _get_client_meta(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    # respect X-Forwarded-For set by reverse proxy
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else None
    return user_agent, ip


@router.post("/login", response_model=TokenResponse, status_code=200)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user_agent, ip = _get_client_meta(request)
    service = AuthService(db)
    return await service.login(
        email=body.email,
        password=body.password,
        user_agent=user_agent,
        ip_address=ip,
    )


@router.post("/refresh", response_model=TokenResponse, status_code=200)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    service = AuthService(db)
    return await service.refresh(body.refresh_token)


@router.post("/logout", response_model=MessageResponse, status_code=200)
async def logout(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    service = AuthService(db)
    await service.logout(body.refresh_token)
    return MessageResponse(message="Logged out successfully")


@router.post("/logout-all", response_model=MessageResponse, status_code=200)
async def logout_all(
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    service = AuthService(db)
    await service.logout_all_devices(str(current_user.user_id))
    return MessageResponse(message="All sessions revoked")


@router.get("/me", response_model=UserMeResponse, status_code=200)
async def me(
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserMeResponse:
    service = AuthService(db)
    return await service.get_me(str(current_user.user_id))
