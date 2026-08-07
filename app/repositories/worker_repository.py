"""
Worker and WorkerDocument repositories.

Both extend BaseRepository to inherit org-scoped CRUD and soft-delete.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker import Worker, WorkerDocument
from app.repositories.base import BaseRepository


class WorkerRepository(BaseRepository[Worker]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Worker, session)

    async def code_exists(self, employee_code: str, org_id: UUID) -> bool:
        result = await self.session.execute(
            select(Worker).where(
                Worker.organization_id == org_id,
                Worker.employee_code == employee_code,
                Worker.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_by_code(self, employee_code: str, org_id: UUID) -> Worker | None:
        result = await self.session.execute(
            select(Worker).where(
                Worker.organization_id == org_id,
                Worker.employee_code == employee_code,
                Worker.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()


class WorkerDocumentRepository(BaseRepository[WorkerDocument]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(WorkerDocument, session)

    async def list_for_worker(
        self,
        worker_id: UUID,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WorkerDocument], int]:
        from sqlalchemy import func

        base_where = [
            WorkerDocument.organization_id == org_id,
            WorkerDocument.worker_id == worker_id,
            WorkerDocument.is_deleted.is_(False),
        ]
        total: int = (
            await self.session.execute(
                select(func.count()).select_from(WorkerDocument).where(*base_where)
            )
        ).scalar_one()

        rows = (
            await self.session.execute(
                select(WorkerDocument)
                .where(*base_where)
                .order_by(WorkerDocument.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return list(rows), total
