"""
Periodic maintenance tasks.
"""

import asyncio
import structlog

from app.tasks.celery_app import celery_app

log = structlog.get_logger(__name__)


@celery_app.task(name="app.tasks.cleanup.prune_expired_refresh_tokens", bind=True, max_retries=3)
def prune_expired_refresh_tokens(self) -> dict:
    """Remove expired refresh tokens. Runs nightly via Beat."""
    async def _run() -> int:
        from app.core.database import AsyncSessionLocal
        from app.repositories.user_repository import RefreshTokenRepository

        async with AsyncSessionLocal() as session:
            repo = RefreshTokenRepository(session)
            count = await repo.delete_expired()
            await session.commit()
            return count

    try:
        count = asyncio.run(_run())
        log.info("pruned_expired_tokens", count=count)
        return {"deleted": count}
    except Exception as exc:
        log.exception("prune_expired_tokens_failed")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
