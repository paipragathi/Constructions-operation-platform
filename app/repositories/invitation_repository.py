import hashlib
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation


class InvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    async def get_by_token(self, raw_token: str) -> Invitation | None:
        token_hash = self.hash_token(raw_token)
        result = await self.session.execute(
            select(Invitation).where(Invitation.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_pending_by_email(self, email: str, org_id: UUID) -> Invitation | None:
        result = await self.session.execute(
            select(Invitation).where(
                Invitation.email == email.lower(),
                Invitation.organization_id == org_id,
                Invitation.accepted_at.is_(None),
                Invitation.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(self, org_id: UUID) -> list[Invitation]:
        result = await self.session.execute(
            select(Invitation)
            .where(Invitation.organization_id == org_id)
            .order_by(Invitation.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, invitation: Invitation) -> Invitation:
        self.session.add(invitation)
        await self.session.flush()
        await self.session.refresh(invitation)
        return invitation

    async def mark_accepted(self, invitation: Invitation) -> Invitation:
        invitation.accepted_at = datetime.now(timezone.utc)
        await self.session.flush()
        return invitation

    async def delete_by_id(self, invitation_id: UUID, org_id: UUID) -> bool:
        result = await self.session.execute(
            delete(Invitation).where(
                Invitation.id == invitation_id,
                Invitation.organization_id == org_id,
                Invitation.accepted_at.is_(None),
            )
        )
        return result.rowcount > 0

    async def delete_expired(self) -> int:
        result = await self.session.execute(
            delete(Invitation).where(
                Invitation.expires_at < datetime.now(timezone.utc),
                Invitation.accepted_at.is_(None),
            )
        )
        return result.rowcount
