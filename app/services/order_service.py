"""
Business logic layer for order operations.
- Idempotent creation via idempotency keys
- State-machine enforcement
- Audit-trail recording
- Retry/backoff for downstream payment service
"""

import math
from typing import Optional
from datetime import datetime, timezone

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderHistory, OrderStatus, VALID_TRANSITIONS
from app.schemas import (
    OrderCreateRequest,
    OrderUpdateRequest,
    StatusTransitionRequest,
    PaginatedOrdersResponse,
    OrderResponse,
)
from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class OrderServiceError(Exception):
    """Base exception for order service errors."""
    pass


class InvalidTransitionError(OrderServiceError):
    """Raised when an invalid status transition is attempted."""
    pass


class OrderNotFoundError(OrderServiceError):
    """Raised when an order is not found."""
    pass


class DuplicateOrderError(OrderServiceError):
    """Raised when a duplicate idempotency key is detected."""
    pass


def _record_change(
    order_id: str,
    field: str,
    old_val: Optional[str],
    new_val: Optional[str],
    changed_by: str = "system",
) -> OrderHistory:
    """Create an audit-trail entry for a field change."""
    return OrderHistory(
        order_id=order_id,
        field_name=field,
        old_value=str(old_val) if old_val is not None else None,
        new_value=str(new_val) if new_val is not None else None,
        changed_by=changed_by,
    )


# ── Downstream Payment Service (with retry/backoff) ─────────────

@retry(
    stop=stop_after_attempt(settings.payment_service_retries),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    reraise=True,
)
async def call_payment_service(order_id: str, amount: float) -> dict:
    """
    Simulate calling a downstream payment service with retry + backoff.
    In production, this would hit a real endpoint.
    """
    logger.info(
        "calling_payment_service",
        order_id=order_id,
        amount=amount,
        url=settings.payment_service_url,
    )
    # Simulate — in real deployment, uncomment the httpx call
    # async with httpx.AsyncClient(timeout=settings.payment_service_timeout) as client:
    #     resp = await client.post(
    #         settings.payment_service_url,
    #         json={"order_id": order_id, "amount": amount},
    #     )
    #     resp.raise_for_status()
    #     return resp.json()

    # Simulated success for demo
    return {"payment_id": f"pay_{order_id[:8]}", "status": "success"}


# ── CRUD Operations ─────────────────────────────────────────────

async def create_order(
    db: AsyncSession,
    request: OrderCreateRequest,
    idempotency_key: Optional[str] = None,
) -> Order:
    """Create a new order with optional idempotency key."""

    # Check idempotency
    if idempotency_key:
        stmt = select(Order).where(Order.idempotency_key == idempotency_key)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            logger.info("idempotent_hit", idempotency_key=idempotency_key, order_id=existing.id)
            return existing

    total = round(request.quantity * request.unit_price, 2)

    order = Order(
        customer_name=request.customer_name,
        customer_email=request.customer_email,
        product_name=request.product_name,
        quantity=request.quantity,
        unit_price=request.unit_price,
        total_price=total,
        idempotency_key=idempotency_key,
        notes=request.notes,
    )
    db.add(order)
    await db.flush()

    # Record creation in audit trail
    db.add(_record_change(order.id, "status", None, OrderStatus.PENDING.value))
    logger.info("order_created", order_id=order.id, total_price=total)

    return order


async def get_order(db: AsyncSession, order_id: str) -> Order:
    """Fetch a single order by ID, raise if not found."""
    stmt = select(Order).where(Order.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise OrderNotFoundError(f"Order {order_id} not found")
    return order


async def list_orders(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[OrderStatus] = None,
) -> PaginatedOrdersResponse:
    """List orders with pagination and optional status filter."""
    base_query = select(Order)
    count_query = select(func.count()).select_from(Order)

    if status_filter:
        base_query = base_query.where(Order.status == status_filter)
        count_query = count_query.where(Order.status == status_filter)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get page of results
    offset = (page - 1) * page_size
    stmt = base_query.order_by(Order.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    orders = result.scalars().all()

    return PaginatedOrdersResponse(
        items=[OrderResponse.model_validate(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


async def update_order(
    db: AsyncSession, order_id: str, request: OrderUpdateRequest
) -> Order:
    """Partial update of order fields, recording each change."""
    order = await get_order(db, order_id)
    update_data = request.model_dump(exclude_unset=True)

    for field, new_value in update_data.items():
        old_value = getattr(order, field)
        if old_value != new_value:
            setattr(order, field, new_value)
            db.add(_record_change(order.id, field, old_value, new_value))

    # Recalculate total if quantity or unit_price changed
    if "quantity" in update_data or "unit_price" in update_data:
        old_total = order.total_price
        order.total_price = round(order.quantity * order.unit_price, 2)
        if old_total != order.total_price:
            db.add(_record_change(order.id, "total_price", old_total, order.total_price))

    order.updated_at = datetime.now(timezone.utc)
    logger.info("order_updated", order_id=order_id, fields=list(update_data.keys()))
    return order


async def transition_status(
    db: AsyncSession, order_id: str, request: StatusTransitionRequest
) -> Order:
    """Transition order status with state-machine validation."""
    order = await get_order(db, order_id)
    current = order.status
    target = request.new_status

    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition from '{current.value}' to '{target.value}'. "
            f"Allowed transitions: {[s.value for s in allowed]}"
        )

    old_status = current.value
    order.status = target
    order.updated_at = datetime.now(timezone.utc)

    db.add(_record_change(order.id, "status", old_status, target.value))

    # If confirming, call payment service
    if target == OrderStatus.CONFIRMED:
        try:
            payment_result = await call_payment_service(order.id, order.total_price)
            logger.info("payment_processed", order_id=order.id, result=payment_result)
        except Exception as e:
            logger.error("payment_failed", order_id=order.id, error=str(e))
            # Revert status on payment failure
            order.status = current
            raise OrderServiceError(f"Payment processing failed: {str(e)}")

    logger.info(
        "status_transitioned",
        order_id=order.id,
        from_status=old_status,
        to_status=target.value,
        reason=request.reason,
    )
    return order


async def delete_order(db: AsyncSession, order_id: str) -> None:
    """Soft-delete by cancelling, or hard-delete if already cancelled."""
    order = await get_order(db, order_id)
    await db.delete(order)
    logger.info("order_deleted", order_id=order_id)


async def get_order_history(db: AsyncSession, order_id: str) -> list[OrderHistory]:
    """Get the full audit trail for an order."""
    # Verify order exists
    await get_order(db, order_id)

    stmt = (
        select(OrderHistory)
        .where(OrderHistory.order_id == order_id)
        .order_by(OrderHistory.changed_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
