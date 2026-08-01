from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    id: UUID
    organization_id: UUID
    email: str
    full_name: str
    role: str
    phone: str | None
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UpdateUserRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: str | None = None
    phone: str | None = Field(default=None, max_length=20)

    def model_post_init(self, __context: object) -> None:
        from app.models.user import UserRole
        if self.role is not None and self.role not in UserRole.ALL_ROLES:
            raise ValueError(f"role must be one of {UserRole.ALL_ROLES}")
