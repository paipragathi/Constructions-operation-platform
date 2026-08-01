"""
Invitation model.

Admins invite users by email + role. The system emails a single-use token link.
The invitee clicks the link, sets a password, and becomes an active User.

Token is stored as SHA-256(raw_token) — raw token lives only in the email.
See ADR-009 for the design rationale.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
        comment="Email address the invitation was sent to",
    )

    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Role the invitee will receive upon acceptance",
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="SHA-256 hex digest of the raw token — never store raw token",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set when the invitee accepts; NULL means still pending",
    )

    invited_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        comment="Admin who created this invitation",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    organization: Mapped["Organization"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Organization",
        lazy="noload",
    )

    invited_by: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        foreign_keys=[invited_by_id],
        lazy="noload",
    )

    @property
    def is_expired(self) -> bool:
        from datetime import timezone
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)

    @property
    def is_accepted(self) -> bool:
        return self.accepted_at is not None

    @property
    def is_pending(self) -> bool:
        return not self.is_accepted and not self.is_expired

    def __repr__(self) -> str:
        return f"<Invitation id={self.id} email={self.email} role={self.role}>"
