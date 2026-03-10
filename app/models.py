"""
SQLAlchemy ORM models for Orders and Order History (audit trail).
"""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Integer, Text, DateTime, Enum, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.database import Base


class OrderStatus(str, enum.Enum):
    """Workflow state machine for orders."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# Valid state transitions
VALID_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Order(Base):
    """Order entity with workflow status."""
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    customer_name = Column(String(255), nullable=False, index=True)
    customer_email = Column(String(255), nullable=False)
    product_name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(
        Enum(OrderStatus),
        nullable=False,
        default=OrderStatus.PENDING,
        index=True,
    )
    idempotency_key = Column(String(255), unique=True, nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship to change history
    history = relationship(
        "OrderHistory", back_populates="order", cascade="all, delete-orphan",
        order_by="OrderHistory.changed_at.desc()"
    )

    __table_args__ = (
        Index("ix_orders_status_created", "status", "created_at"),
    )


class OrderHistory(Base):
    """Audit trail capturing every change to an order."""
    __tablename__ = "order_history"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    order_id = Column(
        String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name = Column(String(100), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_by = Column(String(255), default="system")
    changed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    order = relationship("Order", back_populates="history")
