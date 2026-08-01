from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, org_id: UUID) -> Organization | None:
        return await self.session.get(Organization, org_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self.session.execute(
            select(Organization).where(Organization.slug == slug.lower())
        )
        return result.scalar_one_or_none()

    async def slug_exists(self, slug: str) -> bool:
        result = await self.session.execute(
            select(Organization.id).where(Organization.slug == slug.lower())
        )
        return result.scalar_one_or_none() is not None

    async def create(self, org: Organization) -> Organization:
        self.session.add(org)
        await self.session.flush()
        await self.session.refresh(org)
        return org

    async def update(self, org: Organization) -> Organization:
        await self.session.flush()
        await self.session.refresh(org)
        return org
