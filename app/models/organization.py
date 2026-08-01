"""
Organization model — the top-level tenant in the multi-tenant system.

Every other record in the system belongs to an Organization.
One Organization = one construction company using the platform.

The slug is a URL-safe identifier derived from the company name.
It is used in subdomain routing (future) and as a human-readable tenant ID.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Organization(Base):
    """
    Organization does NOT inherit from TimestampedBase because it IS the tenant.
    It has its own timestamps but no organization_id foreign key (it is the root).
    """

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Company name as registered",
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="URL-safe identifier: 'sharma-constructions'",
    )

    gstin: Mapped[str | None] = mapped_column(
        String(15),
        nullable=True,
        unique=True,
        comment="GST Identification Number — 15 character alphanumeric",
    )

    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    state: Mapped[str | None] = mapped_column(String(100), nullable=True)

    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)

    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="Inactive organizations cannot log in",
    )

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

    # ── Relationships ─────────────────────────────────────────────────────────
    users: Mapped[list["User"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        back_populates="organization",
        lazy="noload",  # always load explicitly — never lazy load in async
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id} slug={self.slug}>"
