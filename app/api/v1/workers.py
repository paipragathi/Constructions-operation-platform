from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import UserInToken, get_current_user, require_role
from app.models.user import UserRole
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.worker import (
    AddWorkerDocumentRequest,
    CreateWorkerRequest,
    UpdateWorkerDocumentRequest,
    UpdateWorkerRequest,
    WorkerDocumentResponse,
    WorkerResponse,
)
from app.services.worker_service import WorkerDocumentService, WorkerService

router = APIRouter(tags=["workers"])

# Roles that can create/update workers
_WRITE_ROLES = (UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.SITE_ENGINEER)
# Roles that can verify documents
_VERIFY_ROLES = (UserRole.ADMIN, UserRole.PROJECT_MANAGER)


# ── Workers ───────────────────────────────────────────────────────────────────

@router.post("/workers", response_model=WorkerResponse, status_code=201)
async def create_worker(
    body: CreateWorkerRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkerResponse:
    return await WorkerService(db).create(body, current_user.organization_id, current_user.user_id)


@router.get("/workers", response_model=PaginatedResponse[WorkerResponse])
async def list_workers(
    trade: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[WorkerResponse]:
    return await WorkerService(db).list_workers(
        current_user.organization_id,
        trade=trade,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )


@router.get("/workers/{worker_id}", response_model=WorkerResponse)
async def get_worker(
    worker_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkerResponse:
    return await WorkerService(db).get(worker_id, current_user.organization_id)


@router.patch("/workers/{worker_id}", response_model=WorkerResponse)
async def update_worker(
    worker_id: UUID,
    body: UpdateWorkerRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkerResponse:
    return await WorkerService(db).update(
        worker_id, current_user.organization_id, body, current_user.user_id
    )


@router.delete("/workers/{worker_id}", response_model=MessageResponse)
async def delete_worker(
    worker_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await WorkerService(db).soft_delete(
        worker_id, current_user.organization_id, current_user.user_id
    )
    return MessageResponse(message="Worker deleted")


# ── Worker Documents ──────────────────────────────────────────────────────────

@router.post(
    "/workers/{worker_id}/documents",
    response_model=WorkerDocumentResponse,
    status_code=201,
)
async def add_worker_document(
    worker_id: UUID,
    body: AddWorkerDocumentRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkerDocumentResponse:
    return await WorkerDocumentService(db).add_document(
        worker_id, current_user.organization_id, body, current_user.user_id
    )


@router.get(
    "/workers/{worker_id}/documents",
    response_model=PaginatedResponse[WorkerDocumentResponse],
)
async def list_worker_documents(
    worker_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[WorkerDocumentResponse]:
    return await WorkerDocumentService(db).list_documents(
        worker_id, current_user.organization_id, page=page, page_size=page_size
    )


@router.get("/worker-documents/{doc_id}", response_model=WorkerDocumentResponse)
async def get_worker_document(
    doc_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkerDocumentResponse:
    return await WorkerDocumentService(db).get_document(doc_id, current_user.organization_id)


@router.patch("/worker-documents/{doc_id}", response_model=WorkerDocumentResponse)
async def update_worker_document(
    doc_id: UUID,
    body: UpdateWorkerDocumentRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkerDocumentResponse:
    return await WorkerDocumentService(db).update_document(
        doc_id, current_user.organization_id, body, current_user.user_id
    )


@router.post("/worker-documents/{doc_id}/verify", response_model=WorkerDocumentResponse)
async def verify_worker_document(
    doc_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_VERIFY_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkerDocumentResponse:
    return await WorkerDocumentService(db).verify_document(
        doc_id, current_user.organization_id, current_user.user_id
    )


@router.delete("/worker-documents/{doc_id}", response_model=MessageResponse)
async def delete_worker_document(
    doc_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await WorkerDocumentService(db).soft_delete_document(
        doc_id, current_user.organization_id, current_user.user_id
    )
    return MessageResponse(message="Document deleted")
