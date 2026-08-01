"""
Structured logging via structlog, routed through stdlib logging.

Development: colored console output.
Production:  JSON, one line per event, parseable by Loki/Datadog/CloudWatch.

Every log line carries: timestamp, level, logger name, and any bound context
keys (request_id, user_id, organization_id injected by middleware).
"""

import logging
import sys

import structlog

from app.core.config import settings


def configure_logging() -> None:
    """Called once from app/main.py lifespan at startup."""
    log_level = getattr(logging, settings.log_level, logging.INFO)

    # Processors shared by both renderers
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
        format_exc = structlog.processors.dict_tracebacks
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
        format_exc = structlog.processors.ExceptionRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            format_exc,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    # Silence noisy libraries in production
    if settings.is_production:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
