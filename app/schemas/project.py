from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=1000)
    start_date: date | None = None
    expected_end_date: date | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    project_manager_id: UUID | None = None

    def model_post_init(self, __context: object) -> None:
        import re
        self.code = self.code.upper().strip()
        if not re.match(r"^[A-Z0-9][A-Z0-9\-]*$", self.code):
            raise ValueError("Project code must be uppercase alphanumeric with hyphens, e.g. HYD-001")


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    start_date: date | None = None
    expected_end_date: date | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    project_manager_id: UUID | None = None


class ProjectStatusTransitionRequest(BaseModel):
    status: str
    reason: str | None = Field(default=None, max_length=500)


class ProjectResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    code: str
    description: str | None
    status: str
    start_date: date | None
    expected_end_date: date | None
    actual_end_date: date | None
    budget: Decimal | None
    project_manager_id: UUID | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateSiteRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)
    site_engineer_id: UUID | None = None


class UpdateSiteRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)
    site_engineer_id: UUID | None = None


class SiteResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    address: str | None
    city: str | None
    state: str | None
    pincode: str | None
    site_engineer_id: UUID | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
