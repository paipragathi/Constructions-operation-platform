"""
Model registry — imports all SQLAlchemy models.

CRITICAL: Every model must be imported here.
Alembic's autogenerate compares the current DB schema against all models
it can find. If a model is not imported here, Alembic will not detect it
and will not generate migrations for it.

Add new models to this file as they are created.
"""

from app.models.base import Base, TimestampedBase
from app.models.invitation import Invitation
from app.models.organization import Organization
from app.models.project import Project, ProjectStatus, Site
from app.models.user import RefreshToken, User, UserRole
from app.models.worker import DocumentType, SkillLevel, Worker, WorkerDocument, WorkerTrade

__all__ = [
    "Base",
    "TimestampedBase",
    "Invitation",
    "Organization",
    "Project",
    "ProjectStatus",
    "Site",
    "User",
    "UserRole",
    "RefreshToken",
    "Worker",
    "WorkerDocument",
    "WorkerTrade",
    "SkillLevel",
    "DocumentType",
]
