from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import UserInToken, get_current_user, require_role
from app.models.user import UserRole
from app.schemas.auth import TokenResponse
from app.schemas.organization import OrganizationResponse, RegisterOrganizationRequest, UpdateOrganizationRequest
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=TokenResponse, status_code=201)
async def register_organization(
    body: RegisterOrganizationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Public endpoint — creates organization + first admin, returns tokens."""
    ua = request.headers.get("user-agent")
    fwd = request.headers.get("x-forwarded-for")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)
    return await OrganizationService(db).register(body, user_agent=ua, ip_address=ip)


@router.get("/me", response_model=OrganizationResponse)
async def get_my_organization(
    current_user: UserInToken = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    return await OrganizationService(db).get_my_org(str(current_user.organization_id))


@router.patch("/me", response_model=OrganizationResponse)
async def update_my_organization(
    body: UpdateOrganizationRequest,
    current_user: UserInToken = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    return await OrganizationService(db).update_my_org(
        str(current_user.organization_id), body, str(current_user.user_id)
    )
