"""
Data-access layer for User and RefreshToken models.
No business logic — only queries.
"""

import hashlib
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import RefreshToken, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_active_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.email == email.lower(),
                User.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        result = await self.session.execute(
            select(User.id).where(User.email == email.lower())
        )
        return result.scalar_one_or_none() is not None

    async def update_last_login(self, user_id: UUID) -> None:
        user = await self.session.get(User, user_id)
        if user:
            user.last_login_at = datetime.now(timezone.utc)
            await self.session.flush()


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def create(self, token: RefreshToken) -> RefreshToken:
        self.session.add(token)
        await self.session.flush()
        await self.session.refresh(token)
        return token

    async def get_by_token(self, raw_token: str) -> RefreshToken | None:
        token_hash = self._hash(raw_token)
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def delete_by_token(self, raw_token: str) -> None:
        token_hash = self._hash(raw_token)
        await self.session.execute(
            delete(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )

    async def delete_all_for_user(self, user_id: UUID) -> None:
        """Revoke all sessions for a user (password change, account compromise)."""
        await self.session.execute(
            delete(RefreshToken).where(RefreshToken.user_id == user_id)
        )

    async def delete_expired(self) -> int:
        """Called by a scheduled Celery task to prune expired tokens."""
        result = await self.session.execute(
            delete(RefreshToken).where(
                RefreshToken.expires_at < datetime.now(timezone.utc)
            )
        )
        return result.rowcount
