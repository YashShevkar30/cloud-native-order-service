"""
Tests for the Cloud-Native Order Service.
Uses SQLite in-memory for fast, isolated tests.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import OrderStatus


# ── Test Database Setup ──────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Sample Data ──────────────────────────────────────────────────

SAMPLE_ORDER = {
    "customer_name": "Alice Johnson",
    "customer_email": "alice@example.com",
    "product_name": "Wireless Headphones",
    "quantity": 2,
    "unit_price": 49.99,
    "notes": "Gift wrapping please",
}


# ── Health Check Tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Health endpoint returns 200."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Root endpoint returns service info."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "Cloud-Native Order Service" in response.json()["service"]


# ── Create Order Tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_order(client: AsyncClient):
    """Successfully create a new order."""
    response = await client.post("/api/v1/orders/", json=SAMPLE_ORDER)
    assert response.status_code == 201
    data = response.json()
    assert data["customer_name"] == "Alice Johnson"
    assert data["quantity"] == 2
    assert data["total_price"] == 99.98
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_create_order_idempotent(client: AsyncClient):
    """Same idempotency key returns the same order."""
    headers = {"Idempotency-Key": "test-key-123"}
    r1 = await client.post("/api/v1/orders/", json=SAMPLE_ORDER, headers=headers)
    r2 = await client.post("/api/v1/orders/", json=SAMPLE_ORDER, headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


@pytest.mark.asyncio
async def test_create_order_validation_error(client: AsyncClient):
    """Invalid data returns 422."""
    bad_order = {**SAMPLE_ORDER, "quantity": -1}
    response = await client.post("/api/v1/orders/", json=bad_order)
    assert response.status_code == 422


# ── Read Order Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_order(client: AsyncClient):
    """Retrieve an existing order by ID."""
    create_resp = await client.post("/api/v1/orders/", json=SAMPLE_ORDER)
    order_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["id"] == order_id


@pytest.mark.asyncio
async def test_get_order_not_found(client: AsyncClient):
    """Non-existent order returns 404."""
    response = await client.get("/api/v1/orders/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_orders_pagination(client: AsyncClient):
    """List endpoint supports pagination."""
    # Create 3 orders
    for _ in range(3):
        await client.post("/api/v1/orders/", json=SAMPLE_ORDER)

    response = await client.get("/api/v1/orders/?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["total_pages"] == 2


@pytest.mark.asyncio
async def test_list_orders_status_filter(client: AsyncClient):
    """Filter orders by status."""
    await client.post("/api/v1/orders/", json=SAMPLE_ORDER)

    response = await client.get("/api/v1/orders/?status=pending")
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    response = await client.get("/api/v1/orders/?status=shipped")
    assert response.status_code == 200
    assert response.json()["total"] == 0


# ── Update Order Tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_order(client: AsyncClient):
    """Partially update an order."""
    create_resp = await client.post("/api/v1/orders/", json=SAMPLE_ORDER)
    order_id = create_resp.json()["id"]

    update_data = {"quantity": 5, "notes": "Updated note"}
    response = await client.patch(f"/api/v1/orders/{order_id}", json=update_data)
    assert response.status_code == 200
    assert response.json()["quantity"] == 5
    assert response.json()["notes"] == "Updated note"


# ── Status Transition Tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_transition(client: AsyncClient):
    """Valid status transition: pending → confirmed."""
    create_resp = await client.post("/api/v1/orders/", json=SAMPLE_ORDER)
    order_id = create_resp.json()["id"]

    response = await client.post(
        f"/api/v1/orders/{order_id}/transition",
        json={"new_status": "confirmed", "reason": "Payment received"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_invalid_transition(client: AsyncClient):
    """Invalid transition: pending → delivered should fail."""
    create_resp = await client.post("/api/v1/orders/", json=SAMPLE_ORDER)
    order_id = create_resp.json()["id"]

    response = await client.post(
        f"/api/v1/orders/{order_id}/transition",
        json={"new_status": "delivered"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_full_workflow(client: AsyncClient):
    """Full lifecycle: pending → confirmed → shipped → delivered."""
    create_resp = await client.post("/api/v1/orders/", json=SAMPLE_ORDER)
    order_id = create_resp.json()["id"]

    for status in ["confirmed", "shipped", "delivered"]:
        resp = await client.post(
            f"/api/v1/orders/{order_id}/transition",
            json={"new_status": status},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == status


# ── History / Audit Trail Tests ──────────────────────────────────

@pytest.mark.asyncio
async def test_order_history(client: AsyncClient):
    """Order history records changes."""
    create_resp = await client.post("/api/v1/orders/", json=SAMPLE_ORDER)
    order_id = create_resp.json()["id"]

    # Make a transition
    await client.post(
        f"/api/v1/orders/{order_id}/transition",
        json={"new_status": "confirmed"},
    )

    response = await client.get(f"/api/v1/orders/{order_id}/history")
    assert response.status_code == 200
    history = response.json()
    assert len(history) >= 2  # Creation + transition


# ── Delete Tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_order(client: AsyncClient):
    """Delete an order."""
    create_resp = await client.post("/api/v1/orders/", json=SAMPLE_ORDER)
    order_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/orders/{order_id}")
    assert response.status_code == 204

    # Verify it's gone
    response = await client.get(f"/api/v1/orders/{order_id}")
    assert response.status_code == 404
