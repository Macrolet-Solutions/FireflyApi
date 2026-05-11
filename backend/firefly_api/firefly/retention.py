"""Daily retention background job for ``firefly_events`` (§7.7).

Runs once per day at a configurable UTC hour (default 03:00) and deletes
rows older than ``events.retentionDays``. Use :class:`RetentionJob`'s
``start`` / ``stop`` for the running service and ``purge_now`` for tests
or manual invocations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.db.models import FireflyEvent

logger = logging.getLogger(__name__)


class RetentionJob:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        retention_days: int,
        *,
        hour: int = 3,
        minute: int = 0,
    ) -> None:
        self._session_factory = session_factory
        self._retention_days = retention_days
        self._hour = hour
        self._minute = minute
        self._scheduler: BackgroundScheduler | None = None

    def start(self) -> None:
        if self._scheduler is not None:
            return
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            self._purge,
            trigger="cron",
            hour=self._hour,
            minute=self._minute,
            id="firefly_events_retention",
            replace_existing=True,
        )
        scheduler.start()
        self._scheduler = scheduler

    def stop(self) -> None:
        if self._scheduler is None:
            return
        self._scheduler.shutdown(wait=False)
        self._scheduler = None

    def purge_now(self) -> int:
        """Synchronously delete expired rows. Returns the number deleted."""
        return self._purge()

    def _purge(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        session = self._session_factory()
        try:
            result = session.execute(
                delete(FireflyEvent).where(FireflyEvent.created_at < cutoff)
            )
            session.commit()
            deleted = result.rowcount or 0
            if deleted:
                logger.info(
                    "Retention purge deleted %d firefly_events rows older than %s",
                    deleted,
                    cutoff.isoformat(),
                )
            return deleted
        except Exception:  # noqa: BLE001
            logger.exception("Retention purge failed")
            session.rollback()
            return 0
        finally:
            session.close()


__all__ = ["RetentionJob"]
