"""
Aggregate router for API v1.

All feature routers are mounted here. main.py includes this single router
under the /api/v1 prefix so the prefix is declared in exactly one place.
"""

from fastapi import APIRouter

from app.api.v1 import auth

router = APIRouter()
router.include_router(auth.router)
