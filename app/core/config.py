"""
Application configuration.

All settings are loaded from environment variables (or .env file).
Every field is typed. Missing required fields cause a startup crash with
a clear error message — not a silent failure three hours later.

Usage:
    from app.core.config import settings
    print(settings.app_name)
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore unknown env vars — don't crash on them
    )

    # ── Application ─────────────────────────────────────────────────────────
    app_name: str = "Construction Platform"
    environment: Literal["development", "testing", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: SecretStr
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_echo: bool = False  # logs every SQL statement — development only

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: SecretStr
    redis_max_connections: int = 50

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480   # 8 hours
    refresh_token_expire_days: int = 30

    # ── Object Storage (S3 / MinIO) ───────────────────────────────────────────
    storage_endpoint_url: str | None = None  # None = real AWS S3
    storage_access_key_id: SecretStr
    storage_secret_access_key: SecretStr
    storage_bucket_name: str = "construction-platform"
    storage_region: str = "ap-south-1"

    # ── Celery ────────────────────────────────────────────────────────────────
    celery_broker_url: SecretStr
    celery_result_backend: SecretStr

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Prometheus ────────────────────────────────────────────────────────────
    metrics_allowed_ips: list[str] = []  # empty = allow all (dev only)

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Enforce stricter rules in production."""
        if self.environment == "production":
            if self.debug:
                raise ValueError("DEBUG must be False in production")
            if self.db_echo:
                raise ValueError("DB_ECHO must be False in production")
            jwt_key = self.jwt_secret_key.get_secret_value()
            if len(jwt_key) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")
        return self

    # ── Convenience properties ─────────────────────────────────────────────────

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def database_url_str(self) -> str:
        return self.database_url.get_secret_value()

    @property
    def redis_url_str(self) -> str:
        return self.redis_url.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns the singleton Settings instance.

    lru_cache ensures Settings is only instantiated once — env vars are read
    once at startup, not on every call. In tests, call get_settings.cache_clear()
    before overriding settings.
    """
    return Settings()


# Module-level singleton for convenient import:
#   from app.core.config import settings
settings = get_settings()
