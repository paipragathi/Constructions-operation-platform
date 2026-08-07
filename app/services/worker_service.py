"""
Worker and WorkerDocument services.

Workers: CRUD with org-scoped employee_code uniqueness.
WorkerDocuments: add, list, update, verify (admin/PM only), soft-delete.

Design note: verification is one-way (False → True). Un-verification is not
a supported business operation in this sprint.
"""

import structlog
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleViolationError,
    ConflictError,
    NotFoundError,
)
from app.models.worker import SkillLevel, Worker, WorkerDocument, WorkerTrade
from app.repositories.worker_repository import WorkerDocumentRepository, WorkerRepository
from app.schemas.common import PaginatedResponse
from app.schemas.worker import (
    AddWorkerDocumentRequest,
    CreateWorkerRequest,
    UpdateWorkerDocumentRequest,
    UpdateWorkerRequest,
    WorkerDocumentResponse,
    WorkerResponse,
)

log = structlog.get_logger(__name__)


class WorkerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._workers = WorkerRepository(session)

    async def create(
        self,
        body: CreateWorkerRequest,
        org_id: UUID,
        created_by: UUID,
    ) -> WorkerResponse:
        if await self._workers.code_exists(body.employee_code, org_id):
            raise ConflictError(
                f"Employee code '{body.employee_code}' already exists in this organization"
            )

        worker = Worker(
            organization_id=org_id,
            employee_code=body.employee_code,
            full_name=body.full_name,
            trade=body.trade,
            skill_level=body.skill_level or SkillLevel.UNSKILLED,
            date_of_birth=body.date_of_birth,
            phone=body.phone,
            emergency_contact_name=body.emergency_contact_name,
            emergency_contact_phone=body.emergency_contact_phone,
            address=body.address,
            city=body.city,
            state=body.state,
            pincode=body.pincode,
            daily_wage_rate=body.daily_wage_rate,
            pf_account_number=body.pf_account_number,
            esi_number=body.esi_number,
            bank_account_number=body.bank_account_number,
            bank_ifsc_code=body.bank_ifsc_code,
            bank_name=body.bank_name,
            registered_by=created_by,
            created_by=created_by,
            updated_by=created_by,
        )
        worker = await self._workers.create(worker)
        log.info("worker_created", worker_id=str(worker.id), code=worker.employee_code)
        return WorkerResponse.model_validate(worker)

    async def list_workers(
        self,
        org_id: UUID,
        *,
        trade: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[WorkerResponse]:
        filters = []
        if trade is not None:
            if trade not in WorkerTrade.ALL_TRADES:
                raise BusinessRuleViolationError(f"Invalid trade filter: {trade}")
            filters.append(Worker.trade == trade)
        if is_active is not None:
            filters.append(Worker.is_active.is_(is_active))

        rows, total = await self._workers.list_all(
            org_id, page=page, page_size=page_size, filters=filters
        )
        items = [WorkerResponse.model_validate(w) for w in rows]
        return PaginatedResponse.build(items, total=total, page=page, page_size=page_size)

    async def get(self, worker_id: UUID, org_id: UUID) -> WorkerResponse:
        worker = await self._get_or_raise(worker_id, org_id)
        return WorkerResponse.model_validate(worker)

    async def update(
        self,
        worker_id: UUID,
        org_id: UUID,
        body: UpdateWorkerRequest,
        updated_by: UUID,
    ) -> WorkerResponse:
        worker = await self._get_or_raise(worker_id, org_id)

        for field, value in body.model_dump(exclude_none=True).items():
            setattr(worker, field, value)
        worker.updated_by = updated_by

        await self._session.flush()
        await self._session.refresh(worker)
        log.info("worker_updated", worker_id=str(worker_id))
        return WorkerResponse.model_validate(worker)

    async def soft_delete(self, worker_id: UUID, org_id: UUID, deleted_by: UUID) -> None:
        worker = await self._get_or_raise(worker_id, org_id)
        await self._workers.soft_delete(worker, deleted_by)
        log.info("worker_deleted", worker_id=str(worker_id))

    async def _get_or_raise(self, worker_id: UUID, org_id: UUID) -> Worker:
        result = await self._session.execute(
            select(Worker).where(
                Worker.id == worker_id,
                Worker.organization_id == org_id,
                Worker.is_deleted.is_(False),
            )
        )
        worker = result.scalar_one_or_none()
        if not worker:
            raise NotFoundError(resource="worker", identifier=str(worker_id))
        return worker


class WorkerDocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._docs = WorkerDocumentRepository(session)
        self._workers = WorkerRepository(session)

    async def add_document(
        self,
        worker_id: UUID,
        org_id: UUID,
        body: AddWorkerDocumentRequest,
        created_by: UUID,
    ) -> WorkerDocumentResponse:
        # Verify worker exists in this org
        worker = await self._workers.get_by_id_or_raise(worker_id, org_id)

        doc = WorkerDocument(
            organization_id=org_id,
            worker_id=worker.id,
            document_type=body.document_type,
            document_number=body.document_number,
            file_key=body.file_key,
            file_name=body.file_name,
            notes=body.notes,
            created_by=created_by,
            updated_by=created_by,
        )
        doc = await self._docs.create(doc)
        log.info(
            "worker_document_added",
            doc_id=str(doc.id),
            worker_id=str(worker_id),
            doc_type=body.document_type,
        )
        return WorkerDocumentResponse.model_validate(doc)

    async def list_documents(
        self,
        worker_id: UUID,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse[WorkerDocumentResponse]:
        # Verify worker exists
        await self._workers.get_by_id_or_raise(worker_id, org_id)
        docs, total = await self._docs.list_for_worker(
            worker_id, org_id, page=page, page_size=page_size
        )
        items = [WorkerDocumentResponse.model_validate(d) for d in docs]
        return PaginatedResponse.build(items, total=total, page=page, page_size=page_size)

    async def get_document(self, doc_id: UUID, org_id: UUID) -> WorkerDocumentResponse:
        doc = await self._get_doc_or_raise(doc_id, org_id)
        return WorkerDocumentResponse.model_validate(doc)

    async def update_document(
        self,
        doc_id: UUID,
        org_id: UUID,
        body: UpdateWorkerDocumentRequest,
        updated_by: UUID,
    ) -> WorkerDocumentResponse:
        doc = await self._get_doc_or_raise(doc_id, org_id)

        for field, value in body.model_dump(exclude_none=True).items():
            setattr(doc, field, value)
        doc.updated_by = updated_by

        await self._session.flush()
        await self._session.refresh(doc)
        return WorkerDocumentResponse.model_validate(doc)

    async def verify_document(
        self,
        doc_id: UUID,
        org_id: UUID,
        verified_by: UUID,
    ) -> WorkerDocumentResponse:
        doc = await self._get_doc_or_raise(doc_id, org_id)

        if doc.verified:
            raise BusinessRuleViolationError("Document is already verified")

        doc.verified = True
        doc.verified_by = verified_by
        doc.verified_at = datetime.now(timezone.utc)
        doc.updated_by = verified_by

        await self._session.flush()
        await self._session.refresh(doc)
        log.info("worker_document_verified", doc_id=str(doc_id), by=str(verified_by))
        return WorkerDocumentResponse.model_validate(doc)

    async def soft_delete_document(
        self, doc_id: UUID, org_id: UUID, deleted_by: UUID
    ) -> None:
        doc = await self._get_doc_or_raise(doc_id, org_id)
        await self._docs.soft_delete(doc, deleted_by)

    async def _get_doc_or_raise(self, doc_id: UUID, org_id: UUID) -> WorkerDocument:
        result = await self._session.execute(
            select(WorkerDocument).where(
                WorkerDocument.id == doc_id,
                WorkerDocument.organization_id == org_id,
                WorkerDocument.is_deleted.is_(False),
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise NotFoundError(resource="worker_document", identifier=str(doc_id))
        return doc
