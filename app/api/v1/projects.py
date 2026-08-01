from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import UserInToken, get_current_user, require_role
from app.models.user import UserRole
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.project import (
    CreateProjectRequest,
    CreateSiteRequest,
    ProjectResponse,
    ProjectStatusTransitionRequest,
    SiteResponse,
    UpdateProjectRequest,
    UpdateSiteRequest,
)
from app.services.project_service import ProjectService, SiteService

router = APIRouter(tags=["projects"])

_WRITE_ROLES = (UserRole.ADMIN, UserRole.PROJECT_MANAGER)


# ── Projects ──────────────────────────────────────────────────────────────────

@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: CreateProjectRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    return await ProjectService(db).create(body, current_user.organization_id, current_user.user_id)


@router.get("/projects", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ProjectResponse]:
    return await ProjectService(db).list_projects(
        current_user.organization_id, status=status, page=page, page_size=page_size
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    return await ProjectService(db).get(project_id, current_user.organization_id)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    body: UpdateProjectRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    return await ProjectService(db).update(
        project_id, current_user.organization_id, body, current_user.user_id
    )


@router.post("/projects/{project_id}/status", response_model=ProjectResponse)
async def transition_project_status(
    project_id: UUID,
    body: ProjectStatusTransitionRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    return await ProjectService(db).transition_status(
        project_id, current_user.organization_id, body, current_user.user_id
    )


@router.delete("/projects/{project_id}", response_model=MessageResponse)
async def delete_project(
    project_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await ProjectService(db).soft_delete(
        project_id, current_user.organization_id, current_user.user_id
    )
    return MessageResponse(message="Project deleted")


# ── Sites ─────────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/sites", response_model=SiteResponse, status_code=201)
async def create_site(
    project_id: UUID,
    body: CreateSiteRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> SiteResponse:
    return await SiteService(db).create(
        project_id, current_user.organization_id, body, current_user.user_id
    )


@router.get("/projects/{project_id}/sites", response_model=PaginatedResponse[SiteResponse])
async def list_sites(
    project_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[SiteResponse]:
    return await SiteService(db).list_sites(
        project_id, current_user.organization_id, page=page, page_size=page_size
    )


@router.get("/sites/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SiteResponse:
    return await SiteService(db).get(site_id, current_user.organization_id)


@router.patch("/sites/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: UUID,
    body: UpdateSiteRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.SITE_ENGINEER)),
    db: AsyncSession = Depends(get_db),
) -> SiteResponse:
    return await SiteService(db).update(
        site_id, current_user.organization_id, body, current_user.user_id
    )


@router.delete("/sites/{site_id}", response_model=MessageResponse)
async def delete_site(
    site_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await SiteService(db).soft_delete(
        site_id, current_user.organization_id, current_user.user_id
    )
    return MessageResponse(message="Site deleted")
