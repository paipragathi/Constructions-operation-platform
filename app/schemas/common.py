"""
Shared schema primitives used across all API modules.
"""

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class CamelModel(BaseModel):
    """Base model that serialises to camelCase for the frontend."""

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
    )


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "PaginatedResponse[T]":
        pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: list[ErrorDetail] | None = None
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    environment: str
    database: bool
    version: str = "1.0.0"


class MessageResponse(BaseModel):
    message: str


class UUIDResponse(BaseModel):
    id: UUID
