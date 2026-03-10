"""
Configuration management using Pydantic Settings.
Reads from environment variables and .env files.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://orders_user:orders_pass@localhost:5432/orders_db"

    # For testing — SQLite fallback
    test_database_url: str = "sqlite+aiosqlite:///./test.db"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    app_port: int = 8000

    # Downstream Services
    payment_service_url: str = "http://localhost:8001/api/payments"
    payment_service_timeout: float = 5.0
    payment_service_retries: int = 3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
