from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RegisterOrganizationRequest(BaseModel):
    """Creates an organization + the first admin user in one transaction."""
    organization_name: str = Field(min_length=2, max_length=200)
    organization_slug: str = Field(min_length=2, max_length=100)
    admin_email: str = Field(min_length=5, max_length=254)
    admin_full_name: str = Field(min_length=2, max_length=200)
    admin_password: str = Field(min_length=8, max_length=128)

    @field_validator("organization_slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        import re
        v = v.lower().strip()
        if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", v):
            raise ValueError("Slug must be lowercase alphanumeric with hyphens, e.g. sharma-constructions")
        return v

    @field_validator("admin_email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    gstin: str | None
    address: str | None
    city: str | None
    state: str | None
    pincode: str | None
    phone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UpdateOrganizationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)
    phone: str | None = Field(default=None, max_length=20)
