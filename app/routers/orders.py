"""
FastAPI router for Order endpoints.
Provides CRUD, status transitions, pagination, and history retrieval.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import OrderStatus
from app.schemas import (
    OrderCreateRequest,
    OrderUpdateRequest,
    StatusTransitionRequest,
    OrderResponse,
    OrderDetailResponse,
    PaginatedOrdersResponse,
    OrderHistoryResponse,
)
from app.services.order_service import (
    create_order,
    get_order,
    list_orders,
    update_order,
    transition_status,
    delete_order,
    get_order_history,
    OrderNotFoundError,
    InvalidTransitionError,
    OrderServiceError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])


# ── Create ───────────────────────────────────────────────────────

@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order_endpoint(
    request: OrderCreateRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new order.

    Pass an `Idempotency-Key` header to ensure at-most-once creation.
    If the same key is sent again, the original order is returned.
    """
    try:
        order = await create_order(db, request, idempotency_key)
        return order
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Read (single) ───────────────────────────────────────────────

@router.get("/{order_id}", response_model=OrderDetailResponse)
async def get_order_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single order by ID, including its change history."""
    try:
        order = await get_order(db, order_id)
        history = await get_order_history(db, order_id)
        response = OrderDetailResponse.model_validate(order)
        response.history = [OrderHistoryResponse.model_validate(h) for h in history]
        return response
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")


# ── Read (list with pagination) ─────────────────────────────────

@router.get("/", response_model=PaginatedOrdersResponse)
async def list_orders_endpoint(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[OrderStatus] = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
):
    """
    List orders with pagination.

    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    - **status**: Optional status filter
    """
    return await list_orders(db, page=page, page_size=page_size, status_filter=status)


# ── Update ───────────────────────────────────────────────────────

@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order_endpoint(
    order_id: str,
    request: OrderUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Partially update an order's fields. Each change is recorded in the audit trail."""
    try:
        return await update_order(db, order_id, request)
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")


# ── Status Transition ───────────────────────────────────────────

@router.post("/{order_id}/transition", response_model=OrderResponse)
async def transition_order_status(
    order_id: str,
    request: StatusTransitionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Transition an order's workflow status.

    Valid transitions:
    - `pending` → `confirmed`, `cancelled`
    - `confirmed` → `shipped`, `cancelled`
    - `shipped` → `delivered`
    - `delivered` → (terminal)
    - `cancelled` → (terminal)
    """
    try:
        return await transition_status(db, order_id, request)
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except OrderServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── History ──────────────────────────────────────────────────────

@router.get("/{order_id}/history", response_model=list[OrderHistoryResponse])
async def get_order_history_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the full audit trail (change history) for an order."""
    try:
        return await get_order_history(db, order_id)
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")


# ── Delete ───────────────────────────────────────────────────────

@router.delete("/{order_id}", status_code=204)
async def delete_order_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete an order and its history."""
    try:
        await delete_order(db, order_id)
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
