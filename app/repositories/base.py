"""
Generic async repository providing CRUD + pagination for any SQLAlchemy model.

Rules:
- Every public method enforces organization_id scoping.
- No business logic here — only data access.
- Services own transactions; the repository only builds queries.
"""

from typing import Any, Generic, Sequence, Type, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import TimestampedBase

ModelT = TypeVar("ModelT", bound=TimestampedBase)


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: Type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, id: UUID, organization_id: UUID) -> ModelT | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.id == id,
                self.model.organization_id == organization_id,
                self.model.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(self, id: UUID, organization_id: UUID) -> ModelT:
        from app.core.exceptions import NotFoundError

        instance = await self.get_by_id(id, organization_id)
        if instance is None:
            raise NotFoundError(
                resource=self.model.__tablename__,
                identifier=str(id),
            )
        return instance

    async def list_all(
        self,
        organization_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        filters: list[Any] | None = None,
        order_by: Any | None = None,
    ) -> tuple[Sequence[ModelT], int]:
        base_where = [
            self.model.organization_id == organization_id,
            self.model.is_deleted.is_(False),
        ]
        if filters:
            base_where.extend(filters)

        count_q = select(func.count()).select_from(self.model).where(*base_where)
        total: int = (await self.session.execute(count_q)).scalar_one()

        q = select(self.model).where(*base_where)
        if order_by is not None:
            q = q.order_by(order_by)
        else:
            q = q.order_by(self.model.created_at.desc())

        offset = (page - 1) * page_size
        q = q.offset(offset).limit(page_size)

        rows = (await self.session.execute(q)).scalars().all()
        return rows, total

    async def create(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()  # get DB-generated id without committing
        await self.session.refresh(instance)
        return instance

    async def soft_delete(self, instance: ModelT, deleted_by_id: UUID) -> ModelT:
        instance.soft_delete(deleted_by_id)
        await self.session.flush()
        return instance
