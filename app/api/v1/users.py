from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import UserInToken, get_current_user, require_role
from app.models.user import UserRole
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.user import UpdateUserRequest, UserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[UserResponse]:
    return await UserService(db).list_users(
        current_user.organization_id, page=page, page_size=page_size
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    return await UserService(db).get_user(user_id, current_user.organization_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    return await UserService(db).update_user(
        user_id, current_user.organization_id, body, current_user.user_id
    )


@router.post("/{user_id}/deactivate", response_model=MessageResponse)
async def deactivate_user(
    user_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await UserService(db).deactivate_user(
        user_id, current_user.organization_id, current_user.user_id
    )
    return MessageResponse(message="User deactivated successfully")
