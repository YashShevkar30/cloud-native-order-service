"""
Pydantic schemas for request validation and response serialization.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr, field_validator
from app.models import OrderStatus


# ── Request Schemas ──────────────────────────────────────────────

class OrderCreateRequest(BaseModel):
    """Schema for creating a new order."""
    customer_name: str = Field(..., min_length=1, max_length=255, examples=["Alice Johnson"])
    customer_email: str = Field(..., max_length=255, examples=["alice@example.com"])
    product_name: str = Field(..., min_length=1, max_length=255, examples=["Wireless Headphones"])
    quantity: int = Field(..., gt=0, le=10000, examples=[2])
    unit_price: float = Field(..., gt=0, examples=[49.99])
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("customer_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v.lower().strip()


class OrderUpdateRequest(BaseModel):
    """Schema for updating order fields (partial update)."""
    customer_name: Optional[str] = Field(None, min_length=1, max_length=255)
    customer_email: Optional[str] = Field(None, max_length=255)
    product_name: Optional[str] = Field(None, min_length=1, max_length=255)
    quantity: Optional[int] = Field(None, gt=0, le=10000)
    unit_price: Optional[float] = Field(None, gt=0)
    notes: Optional[str] = Field(None, max_length=1000)


class StatusTransitionRequest(BaseModel):
    """Schema for transitioning an order's status."""
    new_status: OrderStatus = Field(..., examples=["confirmed"])
    reason: Optional[str] = Field(None, max_length=500, examples=["Payment verified"])


# ── Response Schemas ─────────────────────────────────────────────

class OrderHistoryResponse(BaseModel):
    """A single audit-trail entry."""
    id: str
    field_name: str
    old_value: Optional[str]
    new_value: Optional[str]
    changed_by: str
    changed_at: datetime

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    """Full order response with computed fields."""
    id: str
    customer_name: str
    customer_email: str
    product_name: str
    quantity: int
    unit_price: float
    total_price: float
    status: OrderStatus
    idempotency_key: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderDetailResponse(OrderResponse):
    """Order response including change history."""
    history: List[OrderHistoryResponse] = []


class PaginatedOrdersResponse(BaseModel):
    """Paginated list of orders."""
    items: List[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "1.0.0"
    environment: str
