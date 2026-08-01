# ─────────────────────────────────────────────────────────────────────────────
# Construction Platform — Multi-stage Dockerfile
#
# Stages:
#   base        → Python + uv setup, dependency installation
#   production  → final minimal image (no build tools)
#
# Why multi-stage:
#   Build tools (gcc, git, etc.) needed to compile some packages are NOT
#   needed at runtime. Multi-stage build ensures they never ship to production,
#   reducing the attack surface and image size.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: base — install dependencies ─────────────────────────────────────
FROM python:3.13-slim AS base

# Prevents Python from writing .pyc files (saves disk space)
ENV PYTHONDONTWRITEBYTECODE=1
# Ensures stdout/stderr are unbuffered (logs appear immediately)
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install system dependencies required by asyncpg and cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first (layer cache: only reinstall if these change)
COPY pyproject.toml uv.lock ./

# Install production dependencies only (no dev, no ocr)
# --no-install-project: install deps without installing our package yet
RUN uv sync --frozen --no-install-project --no-dev

# ── Stage 2: production ───────────────────────────────────────────────────────
FROM python:3.13-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime system deps only (no gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from base stage
COPY --from=base /app/.venv /app/.venv

# Make venv binaries available
ENV PATH="/app/.venv/bin:$PATH"

# Copy application source
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Run as non-root user (security: containers should never run as root)
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Run migrations then start the server
# -- Why run migrations here:
#    Migrations are idempotent. Running them at startup ensures the DB schema
#    is always up to date before the app begins serving requests. In production,
#    use a separate init container or deployment hook for more control.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
