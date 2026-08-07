from fastapi import APIRouter

from app.api.v1 import auth, invitations, organizations, projects, users, workers

router = APIRouter()
router.include_router(auth.router)
router.include_router(organizations.router)
router.include_router(users.router)
router.include_router(invitations.router)
router.include_router(projects.router)
router.include_router(workers.router)
