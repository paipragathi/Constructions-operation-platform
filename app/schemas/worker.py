from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateWorkerRequest(BaseModel):
    employee_code: str = Field(min_length=1, max_length=50)
    full_name: str = Field(min_length=2, max_length=200)
    trade: str
    skill_level: str | None = None
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, max_length=20)
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=20)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)
    daily_wage_rate: Decimal | None = Field(default=None, ge=0)
    pf_account_number: str | None = Field(default=None, max_length=50)
    esi_number: str | None = Field(default=None, max_length=50)
    bank_account_number: str | None = Field(default=None, max_length=50)
    bank_ifsc_code: str | None = Field(default=None, max_length=20)
    bank_name: str | None = Field(default=None, max_length=100)

    def model_post_init(self, __context: object) -> None:
        from app.models.worker import SkillLevel, WorkerTrade
        if self.trade not in WorkerTrade.ALL_TRADES:
            raise ValueError(f"trade must be one of {sorted(WorkerTrade.ALL_TRADES)}")
        if self.skill_level is not None and self.skill_level not in SkillLevel.ALL_LEVELS:
            raise ValueError(f"skill_level must be one of {sorted(SkillLevel.ALL_LEVELS)}")
        self.employee_code = self.employee_code.strip().upper()


class UpdateWorkerRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    trade: str | None = None
    skill_level: str | None = None
    phone: str | None = Field(default=None, max_length=20)
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=20)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)
    daily_wage_rate: Decimal | None = Field(default=None, ge=0)
    pf_account_number: str | None = Field(default=None, max_length=50)
    esi_number: str | None = Field(default=None, max_length=50)
    bank_account_number: str | None = Field(default=None, max_length=50)
    bank_ifsc_code: str | None = Field(default=None, max_length=20)
    bank_name: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None

    def model_post_init(self, __context: object) -> None:
        from app.models.worker import SkillLevel, WorkerTrade
        if self.trade is not None and self.trade not in WorkerTrade.ALL_TRADES:
            raise ValueError(f"trade must be one of {sorted(WorkerTrade.ALL_TRADES)}")
        if self.skill_level is not None and self.skill_level not in SkillLevel.ALL_LEVELS:
            raise ValueError(f"skill_level must be one of {sorted(SkillLevel.ALL_LEVELS)}")


class WorkerResponse(BaseModel):
    id: UUID
    organization_id: UUID
    employee_code: str
    full_name: str
    trade: str
    skill_level: str
    date_of_birth: datetime | None
    phone: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    address: str | None
    city: str | None
    state: str | None
    pincode: str | None
    daily_wage_rate: Decimal | None
    pf_account_number: str | None
    esi_number: str | None
    bank_account_number: str | None
    bank_ifsc_code: str | None
    bank_name: str | None
    is_active: bool
    is_deleted: bool
    registered_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Worker Document schemas ───────────────────────────────────────────────────

class AddWorkerDocumentRequest(BaseModel):
    document_type: str
    document_number: str | None = Field(default=None, max_length=100)
    file_key: str | None = Field(default=None, max_length=500)
    file_name: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=1000)

    def model_post_init(self, __context: object) -> None:
        from app.models.worker import DocumentType
        if self.document_type not in DocumentType.ALL_TYPES:
            raise ValueError(f"document_type must be one of {sorted(DocumentType.ALL_TYPES)}")


class UpdateWorkerDocumentRequest(BaseModel):
    document_number: str | None = Field(default=None, max_length=100)
    file_key: str | None = Field(default=None, max_length=500)
    file_name: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=1000)


class WorkerDocumentResponse(BaseModel):
    id: UUID
    organization_id: UUID
    worker_id: UUID
    document_type: str
    document_number: str | None
    file_key: str | None
    file_name: str | None
    verified: bool
    verified_by: UUID | None
    verified_at: datetime | None
    notes: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
