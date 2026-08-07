"""
Worker and WorkerDocument models.

Workers are daily-wage labourers on construction sites. They are distinct
from Users — they never log in. Site engineers register and manage them.

See ADR-011 for design decisions:
  - Trades/skill levels as string constants (not a lookup table)
  - WorkerDocument.file_key is nullable until Sprint 6 (S3 upload)
  - Document verification is a column triplet, not an audit table
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase


class WorkerTrade:
    """Trade constants. String-based so SQLAlchemy stores simple VARCHAR values."""

    MASON = "mason"
    CARPENTER = "carpenter"
    ELECTRICIAN = "electrician"
    PLUMBER = "plumber"
    PAINTER = "painter"
    WELDER = "welder"
    TILE_LAYER = "tile_layer"
    STEEL_FIXER = "steel_fixer"
    HELPER = "helper"
    SUPERVISOR = "supervisor"
    WATCHMAN = "watchman"
    CLEANER = "cleaner"

    ALL_TRADES = {
        MASON, CARPENTER, ELECTRICIAN, PLUMBER, PAINTER,
        WELDER, TILE_LAYER, STEEL_FIXER, HELPER, SUPERVISOR,
        WATCHMAN, CLEANER,
    }


class SkillLevel:
    UNSKILLED = "unskilled"
    SEMI_SKILLED = "semi_skilled"
    SKILLED = "skilled"
    HIGHLY_SKILLED = "highly_skilled"

    ALL_LEVELS = {UNSKILLED, SEMI_SKILLED, SKILLED, HIGHLY_SKILLED}


class DocumentType:
    AADHAAR = "aadhaar"
    PAN = "pan"
    LABOUR_CARD = "labour_card"
    DRIVING_LICENCE = "driving_licence"
    PHOTO = "photo"
    OTHER = "other"

    ALL_TYPES = {AADHAAR, PAN, LABOUR_CARD, DRIVING_LICENCE, PHOTO, OTHER}


class Worker(TimestampedBase):
    """
    Represents a construction labourer or trade worker employed on site.

    employee_code is org-scoped unique (e.g. "W-001"). Admins and PMs
    assign the code; it appears on muster rolls and payslips.
    """

    __tablename__ = "workers"

    # ── Identity ──────────────────────────────────────────────────────────────

    employee_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Org-unique identifier printed on muster rolls, e.g. W-001",
    )

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    trade: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="One of WorkerTrade constants",
    )

    skill_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SkillLevel.UNSKILLED,
        comment="One of SkillLevel constants",
    )

    date_of_birth: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Emergency contact ─────────────────────────────────────────────────────

    emergency_contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Address ───────────────────────────────────────────────────────────────

    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # ── Wage & statutory ─────────────────────────────────────────────────────
    # daily_wage_rate: base daily rate in INR; NUMERIC avoids float rounding
    # pf / esi: statutory registration numbers for payroll deductions

    daily_wage_rate: Mapped[object | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Base daily wage in INR — Numeric avoids float rounding",
    )

    pf_account_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Provident Fund account number",
    )

    esi_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Employee State Insurance number",
    )

    # ── Banking ───────────────────────────────────────────────────────────────

    bank_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_ifsc_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Status ────────────────────────────────────────────────────────────────

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    registered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who first registered this worker",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────

    __table_args__ = (
        Index("ix_workers_org_code", "organization_id", "employee_code", unique=True),
        Index("ix_workers_org_trade", "organization_id", "trade"),
        Index("ix_workers_org_active", "organization_id", "is_active"),
        Index("ix_workers_org_deleted", "organization_id", "is_deleted"),
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    documents: Mapped[list["WorkerDocument"]] = relationship(
        "WorkerDocument",
        back_populates="worker",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Worker id={self.id} code={self.employee_code} name={self.full_name}>"


class WorkerDocument(TimestampedBase):
    """
    A compliance document attached to a worker (Aadhaar, PAN, Labour Card, etc.).

    file_key is nullable in Sprint 3 — actual S3 upload wired in Sprint 6.
    Until then, callers can store document_number and metadata; file_key stays null.

    Verification (verified / verified_by / verified_at) is a column triplet.
    Only admin/PM can mark a document verified via PATCH /documents/{id}/verify.
    """

    __tablename__ = "worker_documents"

    worker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="One of DocumentType constants",
    )

    document_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Aadhaar number, PAN number, Labour Card number, etc.",
    )

    # ── File storage (populated in Sprint 6) ──────────────────────────────────

    file_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="S3/MinIO object key — null until Sprint 6 populates it",
    )

    file_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Original filename shown to the user",
    )

    # ── Verification ──────────────────────────────────────────────────────────

    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Indexes ───────────────────────────────────────────────────────────────

    __table_args__ = (
        Index("ix_worker_docs_org_worker", "organization_id", "worker_id"),
        Index("ix_worker_docs_org_type", "organization_id", "document_type"),
        Index("ix_worker_docs_deleted", "organization_id", "is_deleted"),
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    worker: Mapped[Worker] = relationship(
        "Worker",
        back_populates="documents",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<WorkerDocument id={self.id} type={self.document_type} worker={self.worker_id}>"
