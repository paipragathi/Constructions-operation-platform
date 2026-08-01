from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class InviteUserRequest(BaseModel):
    email: EmailStr
    role: str

    def model_post_init(self, __context: object) -> None:
        from app.models.user import UserRole
        if self.role not in UserRole.ALL_ROLES:
            raise ValueError(f"role must be one of {UserRole.ALL_ROLES}")


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=1)
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class InvitationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    invited_by_id: UUID
    created_at: datetime
    is_pending: bool
    is_expired: bool

    model_config = {"from_attributes": True}


class InvitationValidateResponse(BaseModel):
    email: str
    role: str
    organization_name: str
    is_valid: bool
