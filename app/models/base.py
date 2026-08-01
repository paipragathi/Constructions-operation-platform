"""
SQLAlchemy base models.

TimestampedBase is the base class for every table in the system.
It enforces:
  - UUID primary key (safe to expose in URLs, generatable client-side)
  - organization_id (multi-tenancy — every record belongs to one org)
  - created_at / updated_at (timezone-aware UTC timestamps)
  - created_by / updated_by (which user created/last modified this record)
  - is_deleted / deleted_at / deleted_by (soft delete — never hard delete)

Why server_default for timestamps:
  server_default=func.now() means the DATABASE sets the timestamp, not
  the application. This handles inserts from migrations, scripts, or any
  tool that bypasses the application layer. The DB is the single source
  of truth for time.

Why onupdate for updated_at:
  onupdate=func.now() instructs SQLAlchemy to include updated_at in every
  UPDATE statement automatically. No service code needs to set it manually.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Root declarative base. All models inherit from TimestampedBase, not this."""
    pass


class TimestampedBase(Base):
    """
    Abstract base that every domain table inherits from.
    __abstract__ = True means SQLAlchemy does not create a table for this class.
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Tenant scoping — every query must filter by this",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    # server_default ensures DB sets the value even for direct SQL inserts
    # onupdate ensures updated_at is refreshed on every UPDATE automatically

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Audit ─────────────────────────────────────────────────────────────────
    # nullable: the first admin user has no "created_by" (bootstrapping)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="UUID of the user who created this record",
    )

    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="UUID of the user who last modified this record",
    )

    # ── Soft Delete ───────────────────────────────────────────────────────────
    # Never hard-delete business data. Construction records are legal evidence.
    # All queries must add WHERE is_deleted = false.

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        index=True,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    def soft_delete(self, deleted_by_id: uuid.UUID) -> None:
        """Mark this record as deleted. Does not remove it from the database."""
        from datetime import UTC
        self.is_deleted = True
        self.deleted_at = datetime.now(UTC)
        self.deleted_by = deleted_by_id

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id}>"
