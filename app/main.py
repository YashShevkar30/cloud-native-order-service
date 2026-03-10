"""
FastAPI application entry point.
- Lifespan for DB init/cleanup
- CORS middleware
- Structured logging middleware
- Health check endpoint
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, close_db
from app.middleware.logging import RequestLoggingMiddleware
from app.routers.orders import router as orders_router
from app.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB on startup, dispose on shutdown."""
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="Cloud-Native Order Service",
    description=(
        "A production-ready microservice for managing orders with CRUD operations, "
        "workflow state transitions, idempotent endpoints, pagination, and a full "
        "audit-friendly change history."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ───────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)

# ── Routers ──────────────────────────────────────────────────────

app.include_router(orders_router)


# ── Health Check ─────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.app_env,
    }


@app.get("/", tags=["System"])
async def root():
    """Root endpoint with API information."""
    return {
        "service": "Cloud-Native Order Service",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
