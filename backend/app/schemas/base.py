from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Pagination information for list responses."""

    total: int = Field(..., description="Total number of items", example=100)
    page: int = Field(..., description="Current page number", example=1)
    per_page: int = Field(..., description="Items per page", example=20)
    total_pages: int = Field(..., description="Total number of pages", example=5)


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    data: list[T]
    meta: PaginationMeta


class ErrorResponse(BaseModel):
    """Standard error response format."""

    code: str = Field(
        ..., description="Machine-readable error code", example="VALIDATION_ERROR"
    )
    message: str = Field(
        ..., description="Human-readable error message", example="Invalid input"
    )
    details: dict | None = Field(None, description="Additional error context")
