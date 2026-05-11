"""HTTP tests for segment admin endpoints (§7.3)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _seg_url(device_id: int) -> str:
    return f"/api/v1/admin/fireflies/{device_id}/segments"


def test_create_and_list(client: TestClient, device: dict, segment: dict) -> None:
    r = client.get(_seg_url(device["id"]))
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == segment["id"]


def test_duplicate_channel_segment_returns_409(
    client: TestClient, device: dict, segment: dict
) -> None:
    r = client.post(
        _seg_url(device["id"]),
        json={
            "channel_num": segment["channel_num"],
            "segment_num_in_channel": segment["segment_num_in_channel"],
            "first_led_index": 200,
            "last_led_index": 300,
        },
    )
    assert r.status_code == 409
    assert r.json()["errorCode"] == "segment_conflict"


def test_overlap_on_same_channel_returns_422(
    client: TestClient, device: dict, segment: dict
) -> None:
    # segment spans 1..150 on channel 1.
    r = client.post(
        _seg_url(device["id"]),
        json={
            "channel_num": 1,
            "segment_num_in_channel": 2,
            "first_led_index": 100,
            "last_led_index": 200,
        },
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "segment_overlap"


def test_reverse_direction_overlap_detected(
    client: TestClient, device: dict, segment: dict
) -> None:
    # Same physical LEDs, reverse direction (200 -> 100).
    r = client.post(
        _seg_url(device["id"]),
        json={
            "channel_num": 1,
            "segment_num_in_channel": 2,
            "first_led_index": 200,
            "last_led_index": 100,
        },
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "segment_overlap"


def test_segment_on_different_channel_does_not_overlap(
    client: TestClient, device: dict, segment: dict
) -> None:
    r = client.post(
        _seg_url(device["id"]),
        json={
            "channel_num": 2,
            "segment_num_in_channel": 1,
            "first_led_index": 1,
            "last_led_index": 50,
        },
    )
    assert r.status_code == 201


def test_delete_with_slot_returns_409(
    client: TestClient, device: dict, segment: dict
) -> None:
    slot_resp = client.post(
        f"/api/v1/admin/fireflies/{device['id']}/slots",
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S1",
            "segment_position": 1,
            "num_leds": 10,
        },
    )
    assert slot_resp.status_code == 201, slot_resp.text

    r = client.delete(f"{_seg_url(device['id'])}/{segment['id']}")
    assert r.status_code == 409
    assert r.json()["errorCode"] == "segment_in_use"


def test_unknown_segment_returns_404(client: TestClient, device: dict) -> None:
    r = client.get(f"{_seg_url(device['id'])}/9999")
    assert r.status_code == 404
    assert r.json()["errorCode"] == "segment_not_found"
