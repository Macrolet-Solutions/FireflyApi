"""HTTP tests for slot admin endpoints (§7.4)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _slot_url(device_id: int) -> str:
    return f"/api/v1/admin/fireflies/{device_id}/slots"


def test_create_assigns_slot_index_starting_at_one(
    client: TestClient, device: dict, segment: dict
) -> None:
    r1 = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S1",
            "segment_position": 1,
            "num_leds": 10,
        },
    )
    assert r1.status_code == 201
    assert r1.json()["slot_index"] == 1

    r2 = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S2",
            "segment_position": 11,
            "num_leds": 10,
        },
    )
    assert r2.status_code == 201
    assert r2.json()["slot_index"] == 2


def test_slot_index_is_append_only_after_inserting_earlier_position(
    client: TestClient, device: dict, segment: dict
) -> None:
    # Create S2 first at a higher segment_position.
    client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S2",
            "segment_position": 50,
            "num_leds": 10,
        },
    )
    # Then create S1 at an earlier segment_position. slot_index must still
    # be append-only (2), not renumbered to 1.
    r = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S1",
            "segment_position": 1,
            "num_leds": 10,
        },
    )
    assert r.status_code == 201
    assert r.json()["slot_index"] == 2


def test_overlapping_slots_rejected(
    client: TestClient, device: dict, segment: dict
) -> None:
    client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S1",
            "segment_position": 1,
            "num_leds": 10,
        },
    )
    r = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S2",
            "segment_position": 5,
            "num_leds": 10,
        },
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "slot_overlap"


def test_slot_out_of_segment_rejected(
    client: TestClient, device: dict, segment: dict
) -> None:
    # segment is 150 LEDs; pos 145 + num 10 -> last LED 154 > 150.
    r = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "OUT",
            "segment_position": 145,
            "num_leds": 10,
        },
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "slot_out_of_segment"


def test_duplicate_external_slot_id_returns_409(
    client: TestClient, device: dict, segment: dict
) -> None:
    client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S1",
            "segment_position": 1,
            "num_leds": 10,
        },
    )
    r = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S1",
            "segment_position": 11,
            "num_leds": 10,
        },
    )
    assert r.status_code == 409
    assert r.json()["errorCode"] == "external_slot_id_conflict"


def test_invalid_external_slot_id_regex_rejected(
    client: TestClient, device: dict, segment: dict
) -> None:
    r = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "BAD ID",  # space disallowed
            "segment_position": 1,
            "num_leds": 10,
        },
    )
    assert r.status_code == 422


def test_update_mutates_only_mutable_fields(
    client: TestClient, device: dict, segment: dict
) -> None:
    created = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S1",
            "segment_position": 1,
            "num_leds": 10,
        },
    ).json()
    r = client.put(
        f"{_slot_url(device['id'])}/{created['id']}",
        json={"external_slot_id": "S1B", "label": "Slot 1", "num_leds": 12},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["external_slot_id"] == "S1B"
    assert body["label"] == "Slot 1"
    assert body["num_leds"] == 12
    # segment_position is immutable; original value preserved.
    assert body["segment_position"] == created["segment_position"]


def test_update_num_leds_rechecks_overlap(
    client: TestClient, device: dict, segment: dict
) -> None:
    s1 = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S1",
            "segment_position": 1,
            "num_leds": 10,
        },
    ).json()
    client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S2",
            "segment_position": 11,
            "num_leds": 10,
        },
    )
    # Growing s1 to 15 LEDs would overlap s2.
    r = client.put(
        f"{_slot_url(device['id'])}/{s1['id']}",
        json={"external_slot_id": s1["external_slot_id"], "label": None, "num_leds": 15},
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "slot_overlap"


def test_unknown_slot_returns_404(client: TestClient, device: dict) -> None:
    r = client.get(f"{_slot_url(device['id'])}/9999")
    assert r.status_code == 404
    assert r.json()["errorCode"] == "slot_not_found"
