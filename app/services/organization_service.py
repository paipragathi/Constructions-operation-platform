"""
Organization service.

Handles registration (org + first admin in one transaction) and org updates.
Registration is the only public endpoint — all other org operations require auth.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import create_access_token, generate_refresh_token, hash_password, refresh_token_expiry
from app.core.config import settings
from app.models.organization import Organization
from app.models.user import RefreshToken, User, UserRole
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.schemas.auth import TokenResponse
from app.schemas.organization import OrganizationResponse, RegisterOrganizationRequest, UpdateOrganizationRequest
import hashlib

log = structlog.get_logger(__name__)


class OrganizationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._orgs = OrganizationRepository(session)
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)

    async def register(
        self,
        body: RegisterOrganizationRequest,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenResponse:
        if await self._orgs.slug_exists(body.organization_slug):
            raise ConflictError(f"Organization slug '{body.organization_slug}' is already taken")

        if await self._users.email_exists(body.admin_email):
            raise ConflictError("An account with this email already exists")

        # Create org
        org = Organization(
            name=body.organization_name,
            slug=body.organization_slug.lower(),
        )
        org = await self._orgs.create(org)

        # Create first admin
        admin = User(
            organization_id=org.id,
            email=body.admin_email.lower(),
            full_name=body.admin_full_name,
            password_hash=hash_password(body.admin_password),
            role=UserRole.ADMIN,
        )
        self._session.add(admin)
        await self._session.flush()
        await self._session.refresh(admin)

        # Issue tokens
        raw_token = generate_refresh_token()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        refresh = RefreshToken(
            user_id=admin.id,
            token_hash=token_hash,
            expires_at=refresh_token_expiry(),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self._session.add(refresh)
        await self._session.flush()

        access_token = create_access_token(
            user_id=str(admin.id),
            role=admin.role,
            organization_id=str(org.id),
        )

        log.info("org_registered", org_id=str(org.id), admin_email=admin.email)
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_token,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def get_my_org(self, org_id_str: str) -> OrganizationResponse:
        from uuid import UUID
        org = await self._orgs.get_by_id(UUID(org_id_str))
        if not org:
            raise NotFoundError(resource="organization", identifier=org_id_str)
        return OrganizationResponse.model_validate(org)

    async def update_my_org(
        self, org_id_str: str, body: UpdateOrganizationRequest, updated_by_str: str
    ) -> OrganizationResponse:
        from uuid import UUID
        org = await self._orgs.get_by_id(UUID(org_id_str))
        if not org:
            raise NotFoundError(resource="organization", identifier=org_id_str)

        for field, value in body.model_dump(exclude_none=True).items():
            setattr(org, field, value)

        org = await self._orgs.update(org)
        log.info("org_updated", org_id=org_id_str, updated_by=updated_by_str)
        return OrganizationResponse.model_validate(org)
