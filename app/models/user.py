"""
User model.

A User belongs to exactly one Organization.
Users authenticate via email + password and receive JWT tokens.

Roles (string enum, not a separate table):
  admin            → everything
  project_manager  → approve indents, create POs, view all reports
  site_engineer    → create indents, log daily progress
  supervisor       → mark attendance, create issue slips
  store_keeper     → create GRNs, manage stock
  accounts         → view reports, process payroll

Refresh tokens are stored in a separate table (RefreshToken) so they can
be individually revoked (logout, security incident, admin action).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserRole:
    """Role constants. Not an Enum so SQLAlchemy stores simple strings."""

    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    SITE_ENGINEER = "site_engineer"
    SUPERVISOR = "supervisor"
    STORE_KEEPER = "store_keeper"
    ACCOUNTS = "accounts"

    ALL_ROLES = {ADMIN, PROJECT_MANAGER, SITE_ENGINEER, SUPERVISOR, STORE_KEEPER, ACCOUNTS}


class User(Base):
    """
    User does NOT inherit TimestampedBase — it IS the org member, not a
    business entity owned by the org. But it carries the same soft-delete
    and audit columns for consistency across the codebase.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique within the platform (not per-org) — used for login",
    )

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="bcrypt hash — never store plaintext",
    )

    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=UserRole.SITE_ENGINEER,
        index=True,
        comment="One of UserRole constants",
    )

    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Audit columns (mirrors TimestampedBase for cross-codebase consistency) ──
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

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="User ID of the admin who created this account (None for first admin)",
    )

    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # ── Soft delete ───────────────────────────────────────────────────────────
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

    __table_args__ = (
        Index("ix_users_org_active", "organization_id", "is_active"),
    )

    def soft_delete(self, deleted_by_id: uuid.UUID) -> None:
        from datetime import timezone
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        self.deleted_by = deleted_by_id
        self.is_active = False

    # ── Relationships ─────────────────────────────────────────────────────────
    organization: Mapped["Organization"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Organization",
        back_populates="users",
        lazy="noload",
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        lazy="noload",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


class RefreshToken(Base):
    """
    Stored refresh tokens for revocation support.

    When a user logs out, their refresh token row is deleted.
    When a token is used to refresh, the old row is deleted and a new one
    is inserted (token rotation — limits the window of token theft).
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="SHA-256 hash of the token — never store raw token",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Browser/app that issued this token — for session display",
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="IPv4 or IPv6 of the client at login time",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="refresh_tokens", lazy="noload")

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id}>"
