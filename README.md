# Cloud-Native Order Service

A production-ready microservice for managing orders with CRUD operations, workflow state transitions, idempotent endpoints, pagination, and a full audit-friendly change history.

Built with **Python**, **FastAPI**, **PostgreSQL**, and containerized with **Docker**.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=github-actions&logoColor=white)

---

## Features

### Core Functionality
- **Full CRUD** — Create, Read, Update, Delete orders via RESTful endpoints
- **Pagination** — Cursor-based pagination with configurable page sizes and status filtering
- **Request Validation** — Pydantic-powered input validation with detailed error messages

### Workflow Engine
- **State Machine** — Orders follow a defined lifecycle: `pending → confirmed → shipped → delivered`
- **Guarded Transitions** — Invalid state transitions are rejected with clear error messages
- **Cancellation Support** — Orders can be cancelled from `pending` or `confirmed` states

```
┌─────────┐     ┌───────────┐     ┌─────────┐     ┌───────────┐
│ PENDING │────▶│ CONFIRMED │────▶│ SHIPPED │────▶│ DELIVERED │
└────┬────┘     └─────┬─────┘     └─────────┘     └───────────┘
     │                │
     ▼                ▼
┌───────────┐   ┌───────────┐
│ CANCELLED │   │ CANCELLED │
└───────────┘   └───────────┘
```

### Reliability
- **Idempotent Endpoints** — Pass an `Idempotency-Key` header to prevent duplicate order creation
- **Retry with Backoff** — Downstream payment service calls use exponential backoff (powered by `tenacity`)
- **Structured Logging** — JSON-formatted logs with request-ID correlation for distributed tracing

### Audit Trail
- **Change History** — Every field modification is recorded in `order_history` with before/after values
- **Full Traceability** — Query the complete history of any order via `/api/v1/orders/{id}/history`

### DevOps
- **Containerized** — Multi-stage Dockerfile with health checks and non-root user
- **Docker Compose** — One command to spin up the full stack (API + PostgreSQL)
- **CI Pipeline** — GitHub Actions workflow with linting, tests, Docker build, and smoke tests

---

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/YashShevkar30/cloud-native-order-service.git
cd cloud-native-order-service

# Start the full stack
docker-compose up --build -d

# Verify it's running
curl http://localhost:8000/health
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

### Option 2: Local Development

```bash
# Clone and enter the project
git clone https://github.com/YashShevkar30/cloud-native-order-service.git
cd cloud-native-order-service

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your database credentials

# Run the server
uvicorn app.main:app --reload --port 8000
```

---

## API Reference

### Orders

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/orders/` | Create a new order |
| `GET` | `/api/v1/orders/` | List orders (paginated) |
| `GET` | `/api/v1/orders/{id}` | Get order details + history |
| `PATCH` | `/api/v1/orders/{id}` | Update order fields |
| `POST` | `/api/v1/orders/{id}/transition` | Transition order status |
| `GET` | `/api/v1/orders/{id}/history` | Get audit trail |
| `DELETE` | `/api/v1/orders/{id}` | Delete an order |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc documentation |

### Example: Create an Order

```bash
curl -X POST http://localhost:8000/api/v1/orders/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-abc-123" \
  -d '{
    "customer_name": "Alice Johnson",
    "customer_email": "alice@example.com",
    "product_name": "Wireless Headphones",
    "quantity": 2,
    "unit_price": 49.99
  }'
```

### Example: Transition Status

```bash
curl -X POST http://localhost:8000/api/v1/orders/{order_id}/transition \
  -H "Content-Type: application/json" \
  -d '{
    "new_status": "confirmed",
    "reason": "Payment verified"
  }'
```

---

## Project Structure

```
cloud-native-order-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry, lifespan, middleware
│   ├── config.py             # Pydantic settings management
│   ├── database.py           # Async SQLAlchemy engine + sessions
│   ├── models.py             # ORM models (Order, OrderHistory)
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── middleware/
│   │   └── logging.py        # Structured JSON logging + request-ID
│   ├── routers/
│   │   └── orders.py         # Order API endpoints
│   └── services/
│       └── order_service.py  # Business logic, idempotency, retries
├── tests/
│   └── test_orders.py        # Pytest async test suite
├── docs/
│   └── runbook.md            # Operational runbook
├── .github/
│   └── workflows/
│       └── ci.yml            # GitHub Actions CI pipeline
├── Dockerfile                # Multi-stage container build
├── docker-compose.yml        # Full stack orchestration
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
└── .gitignore
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing
```

Tests use **SQLite in-memory** for fast, isolated execution — no database setup required.

---

## Operational Runbook

See [docs/runbook.md](docs/runbook.md) for:
- Common failure modes and resolution steps
- Database connection troubleshooting
- Payment service timeout handling
- Deployment checklist

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Framework** | FastAPI 0.109 |
| **Language** | Python 3.11 |
| **Database** | PostgreSQL 16 (async via asyncpg) |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Validation** | Pydantic v2 |
| **Logging** | structlog (JSON) |
| **Retries** | tenacity (exponential backoff) |
| **Testing** | pytest + pytest-asyncio + httpx |
| **Container** | Docker + Docker Compose |
| **CI/CD** | GitHub Actions |

---

## License

This project is open source and available under the [MIT License](LICENSE).

## Architecture Notes
Additional architecture documentation to be added here.
