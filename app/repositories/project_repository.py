from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, Site
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Project, session)

    async def code_exists(self, code: str, org_id: UUID, exclude_id: UUID | None = None) -> bool:
        q = select(Project.id).where(
            Project.organization_id == org_id,
            Project.code == code.upper(),
            Project.is_deleted.is_(False),
        )
        if exclude_id:
            q = q.where(Project.id != exclude_id)
        result = await self.session.execute(q)
        return result.scalar_one_or_none() is not None

    async def get_by_code(self, code: str, org_id: UUID) -> Project | None:
        result = await self.session.execute(
            select(Project).where(
                Project.organization_id == org_id,
                Project.code == code.upper(),
                Project.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()


class SiteRepository(BaseRepository[Site]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Site, session)

    async def list_for_project(
        self,
        project_id: UUID,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Site], int]:
        from sqlalchemy import func
        base_where = [
            Site.organization_id == org_id,
            Site.project_id == project_id,
            Site.is_deleted.is_(False),
        ]
        total: int = (
            await self.session.execute(
                select(func.count()).select_from(Site).where(*base_where)
            )
        ).scalar_one()
        rows = (
            await self.session.execute(
                select(Site)
                .where(*base_where)
                .order_by(Site.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return list(rows), total

    async def get_by_id_and_project(
        self, site_id: UUID, project_id: UUID, org_id: UUID
    ) -> Site | None:
        result = await self.session.execute(
            select(Site).where(
                Site.id == site_id,
                Site.project_id == project_id,
                Site.organization_id == org_id,
                Site.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()
