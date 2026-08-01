"""
User management service.

Admins manage users within their organization: list, view, update role/details,
deactivate (soft-delete). Users cannot manage themselves here — profile updates
go through /auth/me.
"""

import structlog
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, BusinessRuleViolationError, NotFoundError
from app.models.user import User, UserRole
from app.schemas.common import PaginatedResponse
from app.schemas.user import UpdateUserRequest, UserResponse

log = structlog.get_logger(__name__)


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_users(
        self,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[UserResponse]:
        from sqlalchemy import func
        base_where = [
            User.organization_id == org_id,
            User.is_deleted.is_(False),
        ]
        total: int = (
            await self._session.execute(
                select(func.count()).select_from(User).where(*base_where)
            )
        ).scalar_one()

        rows = (
            await self._session.execute(
                select(User)
                .where(*base_where)
                .order_by(User.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        items = [UserResponse.model_validate(u) for u in rows]
        return PaginatedResponse.build(items, total=total, page=page, page_size=page_size)

    async def get_user(self, user_id: UUID, org_id: UUID) -> UserResponse:
        user = await self._get_or_raise(user_id, org_id)
        return UserResponse.model_validate(user)

    async def update_user(
        self,
        user_id: UUID,
        org_id: UUID,
        body: UpdateUserRequest,
        updated_by: UUID,
    ) -> UserResponse:
        user = await self._get_or_raise(user_id, org_id)

        # Prevent demoting the last admin
        if body.role and body.role != UserRole.ADMIN and user.role == UserRole.ADMIN:
            admin_count: int = (
                await self._session.execute(
                    select(User).where(
                        User.organization_id == org_id,
                        User.role == UserRole.ADMIN,
                        User.is_active.is_(True),
                        User.is_deleted.is_(False),
                    )
                )
            ).scalars().all().__len__()
            if admin_count <= 1:
                raise BusinessRuleViolationError(
                    "Cannot change role: this is the last admin in the organization"
                )

        for field, value in body.model_dump(exclude_none=True).items():
            setattr(user, field, value)
        user.updated_by = updated_by

        await self._session.flush()
        await self._session.refresh(user)
        log.info("user_updated", user_id=str(user_id), updated_by=str(updated_by))
        return UserResponse.model_validate(user)

    async def deactivate_user(
        self,
        user_id: UUID,
        org_id: UUID,
        deleted_by: UUID,
    ) -> None:
        if user_id == deleted_by:
            raise BusinessRuleViolationError("You cannot deactivate your own account")

        user = await self._get_or_raise(user_id, org_id)

        if user.role == UserRole.ADMIN:
            admin_count = len(
                (
                    await self._session.execute(
                        select(User).where(
                            User.organization_id == org_id,
                            User.role == UserRole.ADMIN,
                            User.is_active.is_(True),
                            User.is_deleted.is_(False),
                        )
                    )
                ).scalars().all()
            )
            if admin_count <= 1:
                raise BusinessRuleViolationError(
                    "Cannot deactivate the last admin in the organization"
                )

        user.soft_delete(deleted_by)
        await self._session.flush()
        log.info("user_deactivated", user_id=str(user_id), by=str(deleted_by))

    async def _get_or_raise(self, user_id: UUID, org_id: UUID) -> User:
        result = await self._session.execute(
            select(User).where(User.id == user_id, User.is_deleted.is_(False))
        )
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundError(resource="user", identifier=str(user_id))
        if user.organization_id != org_id:
            raise AuthorizationError("User does not belong to your organization")
        return user
