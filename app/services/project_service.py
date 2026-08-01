"""
Project and Site services.

Project state machine enforcement lives here — not in the model, not in the router.
See ADR-010 for the rationale.
"""

import structlog
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleViolationError,
    ConflictError,
    InvalidStatusTransitionError,
    NotFoundError,
)
from app.models.project import Project, ProjectStatus, Site
from app.repositories.project_repository import ProjectRepository, SiteRepository
from app.schemas.common import PaginatedResponse
from app.schemas.project import (
    CreateProjectRequest,
    CreateSiteRequest,
    ProjectResponse,
    ProjectStatusTransitionRequest,
    SiteResponse,
    UpdateProjectRequest,
    UpdateSiteRequest,
)

log = structlog.get_logger(__name__)


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._projects = ProjectRepository(session)

    async def create(
        self,
        body: CreateProjectRequest,
        org_id: UUID,
        created_by: UUID,
    ) -> ProjectResponse:
        if await self._projects.code_exists(body.code, org_id):
            raise ConflictError(f"Project code '{body.code}' already exists in this organization")

        project = Project(
            organization_id=org_id,
            name=body.name,
            code=body.code.upper(),
            description=body.description,
            status=ProjectStatus.DRAFT,
            start_date=body.start_date,
            expected_end_date=body.expected_end_date,
            budget=body.budget,
            project_manager_id=body.project_manager_id,
            created_by=created_by,
            updated_by=created_by,
        )
        project = await self._projects.create(project)
        log.info("project_created", project_id=str(project.id), code=project.code)
        return ProjectResponse.model_validate(project)

    async def list_projects(
        self,
        org_id: UUID,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[ProjectResponse]:
        filters = []
        if status:
            if status not in ProjectStatus.ALL:
                raise BusinessRuleViolationError(f"Invalid status filter: {status}")
            filters.append(Project.status == status)

        rows, total = await self._projects.list_all(
            org_id, page=page, page_size=page_size, filters=filters
        )
        items = [ProjectResponse.model_validate(p) for p in rows]
        return PaginatedResponse.build(items, total=total, page=page, page_size=page_size)

    async def get(self, project_id: UUID, org_id: UUID) -> ProjectResponse:
        project = await self._projects.get_by_id_or_raise(project_id, org_id)
        return ProjectResponse.model_validate(project)

    async def update(
        self,
        project_id: UUID,
        org_id: UUID,
        body: UpdateProjectRequest,
        updated_by: UUID,
    ) -> ProjectResponse:
        project = await self._projects.get_by_id_or_raise(project_id, org_id)

        if project.status == ProjectStatus.CLOSED:
            raise BusinessRuleViolationError("Cannot update a closed project")

        for field, value in body.model_dump(exclude_none=True).items():
            setattr(project, field, value)
        project.updated_by = updated_by

        await self._session.flush()
        await self._session.refresh(project)
        return ProjectResponse.model_validate(project)

    async def transition_status(
        self,
        project_id: UUID,
        org_id: UUID,
        body: ProjectStatusTransitionRequest,
        updated_by: UUID,
    ) -> ProjectResponse:
        project = await self._projects.get_by_id_or_raise(project_id, org_id)

        if not ProjectStatus.can_transition(project.status, body.status):
            raise InvalidStatusTransitionError(
                f"Cannot transition project from '{project.status}' to '{body.status}'"
            )

        project.status = body.status
        project.updated_by = updated_by

        if body.status == ProjectStatus.CLOSED:
            project.actual_end_date = date.today()

        await self._session.flush()
        await self._session.refresh(project)
        log.info(
            "project_status_changed",
            project_id=str(project_id),
            from_status=project.status,
            to_status=body.status,
        )
        return ProjectResponse.model_validate(project)

    async def soft_delete(self, project_id: UUID, org_id: UUID, deleted_by: UUID) -> None:
        project = await self._projects.get_by_id_or_raise(project_id, org_id)
        if project.status not in (ProjectStatus.DRAFT, ProjectStatus.CLOSED):
            raise BusinessRuleViolationError(
                "Only draft or closed projects can be deleted"
            )
        await self._projects.soft_delete(project, deleted_by)


class SiteService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sites = SiteRepository(session)
        self._projects = ProjectRepository(session)

    async def create(
        self,
        project_id: UUID,
        org_id: UUID,
        body: CreateSiteRequest,
        created_by: UUID,
    ) -> SiteResponse:
        project = await self._projects.get_by_id_or_raise(project_id, org_id)
        if project.status == ProjectStatus.CLOSED:
            raise BusinessRuleViolationError("Cannot add a site to a closed project")

        site = Site(
            organization_id=org_id,
            project_id=project_id,
            name=body.name,
            address=body.address,
            city=body.city,
            state=body.state,
            pincode=body.pincode,
            site_engineer_id=body.site_engineer_id,
            created_by=created_by,
            updated_by=created_by,
        )
        self._session.add(site)
        await self._session.flush()
        await self._session.refresh(site)
        log.info("site_created", site_id=str(site.id), project_id=str(project_id))
        return SiteResponse.model_validate(site)

    async def list_sites(
        self,
        project_id: UUID,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse[SiteResponse]:
        rows, total = await self._sites.list_for_project(
            project_id, org_id, page=page, page_size=page_size
        )
        items = [SiteResponse.model_validate(s) for s in rows]
        return PaginatedResponse.build(items, total=total, page=page, page_size=page_size)

    async def get(self, site_id: UUID, org_id: UUID) -> SiteResponse:
        site = await self._sites.get_by_id_or_raise(site_id, org_id)
        return SiteResponse.model_validate(site)

    async def update(
        self,
        site_id: UUID,
        org_id: UUID,
        body: UpdateSiteRequest,
        updated_by: UUID,
    ) -> SiteResponse:
        site = await self._sites.get_by_id_or_raise(site_id, org_id)

        for field, value in body.model_dump(exclude_none=True).items():
            setattr(site, field, value)
        site.updated_by = updated_by

        await self._session.flush()
        await self._session.refresh(site)
        return SiteResponse.model_validate(site)

    async def soft_delete(self, site_id: UUID, org_id: UUID, deleted_by: UUID) -> None:
        site = await self._sites.get_by_id_or_raise(site_id, org_id)
        await self._sites.soft_delete(site, deleted_by)
