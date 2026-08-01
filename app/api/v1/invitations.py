from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import UserInToken, get_current_user, require_role
from app.models.user import UserRole
from app.schemas.common import MessageResponse
from app.schemas.invitation import (
    AcceptInvitationRequest,
    InvitationResponse,
    InvitationValidateResponse,
    InviteUserRequest,
)
from app.services.invitation_service import InvitationService

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post("", response_model=InvitationResponse, status_code=201)
async def invite_user(
    body: InviteUserRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> InvitationResponse:
    return await InvitationService(db).invite(
        body,
        org_id_str=str(current_user.organization_id),
        invited_by_id_str=str(current_user.user_id),
    )


@router.get("/validate", response_model=InvitationValidateResponse)
async def validate_invitation(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> InvitationValidateResponse:
    """Public endpoint — frontend calls this when the user clicks the invite link."""
    return await InvitationService(db).validate_token(token)


@router.post("/accept", response_model=MessageResponse, status_code=200)
async def accept_invitation(
    body: AcceptInvitationRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Public endpoint — invitee sets their password and creates their account."""
    await InvitationService(db).accept(body)
    return MessageResponse(message="Account created successfully. You can now log in.")


@router.get("", response_model=list[InvitationResponse])
async def list_invitations(
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[InvitationResponse]:
    return await InvitationService(db).list_invitations(str(current_user.organization_id))


@router.delete("/{invitation_id}", response_model=MessageResponse)
async def revoke_invitation(
    invitation_id: UUID,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await InvitationService(db).revoke(
        str(invitation_id), str(current_user.organization_id)
    )
    return MessageResponse(message="Invitation revoked")
