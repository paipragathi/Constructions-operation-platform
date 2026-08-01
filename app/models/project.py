"""
Project and Site models.

A Project is the top-level container for all construction work.
A Site is a physical location within a project (e.g., Block A, Block B).

Status machine (see ADR-010):
  draft → active → on_hold ↔ active
                 ↓         ↓
               closed ← on_hold

All business logic for status transitions lives in ProjectService.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase


class ProjectStatus:
    DRAFT = "draft"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    CLOSED = "closed"

    ALL = {DRAFT, ACTIVE, ON_HOLD, CLOSED}

    # Transition table: current_status → set of allowed next statuses
    ALLOWED_TRANSITIONS: dict[str, set[str]] = {
        DRAFT:    {ACTIVE},
        ACTIVE:   {ON_HOLD, CLOSED},
        ON_HOLD:  {ACTIVE, CLOSED},
        CLOSED:   set(),
    }

    @classmethod
    def can_transition(cls, current: str, next_status: str) -> bool:
        return next_status in cls.ALLOWED_TRANSITIONS.get(current, set())


class Project(TimestampedBase):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Short identifier unique within the org, e.g. HYD-001",
    )

    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ProjectStatus.DRAFT,
        server_default=text("'draft'"),
        index=True,
    )

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    expected_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    actual_end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Set when project transitions to closed",
    )

    budget: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        comment="Total approved budget in INR",
    )

    project_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    project_manager: Mapped["User | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        foreign_keys=[project_manager_id],
        lazy="noload",
    )

    sites: Mapped[list["Site"]] = relationship(
        "Site",
        back_populates="project",
        lazy="noload",
    )

    # ── Composite indexes ─────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_projects_org_code", "organization_id", "code", unique=True),
        Index("ix_projects_org_status", "organization_id", "status"),
        Index("ix_projects_org_deleted", "organization_id", "is_deleted"),
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} code={self.code} status={self.status}>"


class Site(TimestampedBase):
    __tablename__ = "sites"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    state: Mapped[str | None] = mapped_column(String(100), nullable=True)

    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)

    site_engineer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Primary site engineer responsible for this site",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    project: Mapped[Project] = relationship(
        "Project",
        back_populates="sites",
        lazy="noload",
    )

    site_engineer: Mapped["User | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        foreign_keys=[site_engineer_id],
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_sites_org_project", "organization_id", "project_id"),
        Index("ix_sites_org_deleted", "organization_id", "is_deleted"),
    )

    def __repr__(self) -> str:
        return f"<Site id={self.id} name={self.name} project_id={self.project_id}>"
