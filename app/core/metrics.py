"""
Prometheus metrics definitions.

HTTP metrics are handled automatically by prometheus-fastapi-instrumentator.
This module defines additional business and infrastructure metrics that
must be incremented manually in services.

Usage:
    from app.core.metrics import INDENT_CREATED
    INDENT_CREATED.labels(organization_id=str(org_id), status="DRAFT").inc()

Metrics are initialized at import time. Prometheus scrapes them from /metrics.
"""

from prometheus_client import Counter, Gauge, Histogram

# ── Authentication ─────────────────────────────────────────────────────────────
AUTH_LOGIN_ATTEMPTS = Counter(
    "auth_login_attempts_total",
    "Total login attempts",
    ["status"],  # "success" | "failed"
)

AUTH_TOKEN_REFRESH = Counter(
    "auth_token_refresh_total",
    "Total token refresh attempts",
    ["status"],
)

# ── Business Events ────────────────────────────────────────────────────────────
INDENT_CREATED = Counter(
    "indents_created_total",
    "Total material indents created",
    ["organization_id"],
)

INDENT_STATUS_CHANGED = Counter(
    "indent_status_changes_total",
    "Total indent status transitions",
    ["organization_id", "from_status", "to_status"],
)

GRN_PROCESSED = Counter(
    "grn_processed_total",
    "Total goods receipt notes processed",
    ["organization_id"],
)

MATERIAL_ISSUED = Counter(
    "material_issues_total",
    "Total material issue slips created",
    ["organization_id"],
)

PAYROLL_RUNS = Counter(
    "payroll_runs_total",
    "Total payroll computation runs",
    ["organization_id", "status"],  # "success" | "failed"
)

RA_BILLS_GENERATED = Counter(
    "ra_bills_generated_total",
    "Total RA bills generated",
    ["organization_id"],
)

# ── Infrastructure ─────────────────────────────────────────────────────────────
CACHE_HITS = Counter(
    "redis_cache_hits_total",
    "Total Redis cache hits",
    ["cache_key_prefix"],
)

CACHE_MISSES = Counter(
    "redis_cache_misses_total",
    "Total Redis cache misses",
    ["cache_key_prefix"],
)

S3_UPLOAD_DURATION = Histogram(
    "s3_upload_duration_seconds",
    "Time taken to upload a file to S3/MinIO",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

S3_UPLOADS = Counter(
    "s3_uploads_total",
    "Total S3 upload attempts",
    ["status"],  # "success" | "failed"
)

# ── Celery Tasks ───────────────────────────────────────────────────────────────
CELERY_TASK_DURATION = Histogram(
    "celery_task_duration_seconds",
    "Time taken to complete a Celery task",
    ["task_name"],
    buckets=[1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0],
)

CELERY_TASKS = Counter(
    "celery_tasks_total",
    "Total Celery task executions",
    ["task_name", "status"],  # "success" | "failed"
)

# ── Database ──────────────────────────────────────────────────────────────────
DB_POOL_SIZE = Gauge(
    "db_connection_pool_size",
    "Current database connection pool size",
)

DB_POOL_CHECKED_OUT = Gauge(
    "db_connections_checked_out",
    "Number of database connections currently in use",
)
