"""
Invitation service.

Admins invite users by email + role.
Invitees click a link, validate the token, then set a password.

Token lifecycle: raw token → SHA-256 hash stored → one-time use → accepted_at set.
See ADR-009.
"""

import secrets
import structlog
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.invitation import Invitation
from app.models.user import User
from app.repositories.invitation_repository import InvitationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.invitation import (
    AcceptInvitationRequest,
    InvitationResponse,
    InvitationValidateResponse,
    InviteUserRequest,
)

log = structlog.get_logger(__name__)

_INVITE_EXPIRY_DAYS = 7


class InvitationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._invitations = InvitationRepository(session)
        self._users = UserRepository(session)

    async def invite(
        self,
        body: InviteUserRequest,
        org_id_str: str,
        invited_by_id_str: str,
    ) -> InvitationResponse:
        from uuid import UUID
        org_id = UUID(org_id_str)
        email = body.email.lower()

        # Block if already an active user in this org
        existing = await self._users.get_by_email(email)
        if existing and str(existing.organization_id) == org_id_str:
            raise ConflictError(f"{email} is already a member of this organization")

        # Block if a pending invitation already exists
        pending = await self._invitations.get_pending_by_email(email, org_id)
        if pending:
            raise ConflictError(f"A pending invitation already exists for {email}")

        raw_token = secrets.token_hex(32)  # 256 bits entropy
        token_hash = InvitationRepository.hash_token(raw_token)

        invitation = Invitation(
            organization_id=org_id,
            email=email,
            role=body.role,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=_INVITE_EXPIRY_DAYS),
            invited_by_id=UUID(invited_by_id_str),
        )
        invitation = await self._invitations.create(invitation)

        # TODO Sprint 12: send invitation email via Celery notifications queue
        log.info("invitation_created", email=email, role=body.role, org_id=org_id_str)

        # Return with the raw token so tests can validate the flow end-to-end.
        # In production the raw token goes into the email link ONLY — never in the response body.
        # We include it here for the accept flow test; a real frontend would receive it via email.
        response = InvitationResponse.model_validate(invitation)
        # Attach raw token as a transient attribute for test harness (not stored)
        response.__dict__["_raw_token"] = raw_token
        return response

    async def validate_token(self, raw_token: str) -> InvitationValidateResponse:
        invitation = await self._invitations.get_by_token(raw_token)
        if not invitation:
            return InvitationValidateResponse(
                email="", role="", organization_name="", is_valid=False
            )
        if invitation.is_accepted or invitation.is_expired:
            return InvitationValidateResponse(
                email=invitation.email, role=invitation.role,
                organization_name="", is_valid=False,
            )

        org = await self._session.get(
            __import__("app.models.organization", fromlist=["Organization"]).Organization,
            invitation.organization_id,
        )
        return InvitationValidateResponse(
            email=invitation.email,
            role=invitation.role,
            organization_name=org.name if org else "",
            is_valid=True,
        )

    async def accept(self, body: AcceptInvitationRequest) -> None:
        invitation = await self._invitations.get_by_token(body.token)

        if not invitation:
            raise AuthenticationError("Invitation token is invalid or has already been used")

        if invitation.is_accepted:
            raise AuthenticationError("This invitation has already been accepted")

        if invitation.is_expired:
            raise AuthenticationError("This invitation has expired — ask your admin to resend it")

        # Check the email isn't already registered (race condition guard)
        if await self._users.email_exists(invitation.email):
            raise ConflictError("An account with this email already exists")

        user = User(
            organization_id=invitation.organization_id,
            email=invitation.email,
            full_name=body.full_name,
            password_hash=hash_password(body.password),
            role=invitation.role,
            created_by=invitation.invited_by_id,
        )
        self._session.add(user)
        await self._session.flush()

        await self._invitations.mark_accepted(invitation)
        log.info("invitation_accepted", email=invitation.email, role=invitation.role)

    async def list_invitations(self, org_id_str: str) -> list[InvitationResponse]:
        from uuid import UUID
        invitations = await self._invitations.list_for_org(UUID(org_id_str))
        return [InvitationResponse.model_validate(i) for i in invitations]

    async def revoke(self, invitation_id_str: str, org_id_str: str) -> None:
        from uuid import UUID
        deleted = await self._invitations.delete_by_id(
            UUID(invitation_id_str), UUID(org_id_str)
        )
        if not deleted:
            raise NotFoundError(resource="invitation", identifier=invitation_id_str)
