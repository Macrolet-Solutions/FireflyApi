"""Tests for the daily retention job (§7.7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.db.models import FireflyEvent
from firefly_api.firefly.retention import RetentionJob


def _make_event(
    db: Session,
    device_id: int,
    *,
    days_old: float,
    event_type: str = "init_slots_sent",
) -> FireflyEvent:
    when = datetime.now(timezone.utc) - timedelta(days=days_old)
    event = FireflyEvent(
        device_id=device_id,
        event_id=f"evt-{days_old}",
        event_type=event_type,
        created_at=when,
    )
    db.add(event)
    db.commit()
    return event


def test_purge_now_deletes_only_expired_rows(
    session_factory: sessionmaker[Session], device: dict
) -> None:
    with session_factory() as db:
        _make_event(db, device["id"], days_old=45.0)  # expired
        _make_event(db, device["id"], days_old=31.0)  # expired
        _make_event(db, device["id"], days_old=29.0)  # kept
        _make_event(db, device["id"], days_old=0.1)  # kept

    job = RetentionJob(session_factory, retention_days=30)
    deleted = job.purge_now()
    assert deleted == 2

    with session_factory() as db:
        remaining = db.scalars(select(FireflyEvent)).all()
    assert len(remaining) == 2
    assert all(
        (datetime.now(timezone.utc) - r.created_at.replace(tzinfo=timezone.utc))
        < timedelta(days=30)
        for r in remaining
    )


def test_purge_now_returns_zero_when_nothing_expired(
    session_factory: sessionmaker[Session], device: dict
) -> None:
    with session_factory() as db:
        _make_event(db, device["id"], days_old=1.0)

    job = RetentionJob(session_factory, retention_days=30)
    assert job.purge_now() == 0


def test_start_and_stop_lifecycle(session_factory: sessionmaker[Session]) -> None:
    job = RetentionJob(session_factory, retention_days=30, hour=3, minute=0)
    job.start()
    try:
        # Starting twice is a no-op.
        job.start()
    finally:
        job.stop()
    # Stopping twice is a no-op.
    job.stop()
