"""HTTP tests for ``/api/v1/admin/events`` (§7.7, §9)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.db.models import FireflyEvent


def _make(
    db: Session,
    device_id: int,
    event_type: str,
    *,
    event_id: str = "evt",
) -> FireflyEvent:
    row = FireflyEvent(
        device_id=device_id,
        event_id=event_id,
        event_type=event_type,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row


def test_empty_returns_empty_list(client: TestClient) -> None:
    r = client.get("/api/v1/admin/events")
    assert r.status_code == 200
    assert r.json() == []


def test_list_filters_by_device(
    client: TestClient, session_factory: sessionmaker[Session], device: dict
) -> None:
    other = client.post(
        "/api/v1/admin/fireflies",
        json={"name": "FF02", "mqtt_broker_id": device["mqtt_broker_id"]},
    ).json()
    with session_factory() as db:
        _make(db, device["id"], "init_slots_sent", event_id="a")
        _make(db, other["id"], "init_slots_sent", event_id="b")

    r = client.get(f"/api/v1/admin/events?deviceId={device['id']}")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["deviceId"] == device["id"]


def test_list_filters_by_event_type(
    client: TestClient, session_factory: sessionmaker[Session], device: dict
) -> None:
    with session_factory() as db:
        _make(db, device["id"], "init_slots_sent", event_id="a")
        _make(db, device["id"], "ack_received", event_id="b")

    r = client.get(
        f"/api/v1/admin/events?deviceId={device['id']}&eventType=ack_received"
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["eventType"] == "ack_received"


def test_list_returns_most_recent_first_and_paginates(
    client: TestClient, session_factory: sessionmaker[Session], device: dict
) -> None:
    with session_factory() as db:
        for i in range(5):
            _make(db, device["id"], "ack_received", event_id=f"e{i}")

    r = client.get("/api/v1/admin/events?limit=3")
    rows = r.json()
    assert len(rows) == 3
    # IDs descending.
    assert rows[0]["id"] > rows[1]["id"] > rows[2]["id"]

    # Pagination: ask for the next page using beforeId.
    cutoff = rows[-1]["id"]
    r2 = client.get(f"/api/v1/admin/events?limit=3&beforeId={cutoff}")
    rows2 = r2.json()
    assert all(row["id"] < cutoff for row in rows2)


def test_get_single_event(
    client: TestClient, session_factory: sessionmaker[Session], device: dict
) -> None:
    with session_factory() as db:
        row = _make(db, device["id"], "init_slots_sent")
        row_id = row.id
    r = client.get(f"/api/v1/admin/events/{row_id}")
    assert r.status_code == 200
    assert r.json()["id"] == row_id


def test_get_unknown_event_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/admin/events/9999")
    assert r.status_code == 404
    assert r.json()["errorCode"] == "event_not_found"
