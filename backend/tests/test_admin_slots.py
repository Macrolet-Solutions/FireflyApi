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
            "segment_position": 2,
            "num_leds": 10,
        },
    )
    assert r2.status_code == 201
    assert r2.json()["slot_index"] == 2


def test_slot_index_uses_next_controller_index_after_inserting_earlier_position(
    client: TestClient, device: dict, segment: dict
) -> None:
    # Create S2 first at a higher segment_position.
    client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S2",
            "segment_position": 2,
            "num_leds": 10,
        },
    )
    # Then create S1 at an earlier segment_position. slot_index is still the
    # next controller-wide index (2), not derived from segment_position.
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


def test_delete_compacts_slot_indexes_across_controller_channels(
    client: TestClient, device: dict, segment: dict
) -> None:
    r_segment2 = client.post(
        f"/api/v1/admin/fireflies/{device['id']}/segments",
        json={
            "channel_num": 2,
            "segment_num_in_channel": 1,
            "first_led_index": 1,
            "last_led_index": 150,
        },
    )
    assert r_segment2.status_code == 201, r_segment2.text
    segment2 = r_segment2.json()

    s1 = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S1",
            "segment_position": 1,
            "num_leds": 10,
        },
    ).json()
    s2 = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S2",
            "segment_position": 2,
            "num_leds": 10,
        },
    ).json()
    s3 = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment2["id"],
            "external_slot_id": "S3",
            "segment_position": 1,
            "num_leds": 10,
        },
    ).json()

    r_delete = client.delete(f"{_slot_url(device['id'])}/{s2['id']}")
    assert r_delete.status_code == 204

    r_list = client.get(_slot_url(device["id"]))
    assert r_list.status_code == 200
    slots = r_list.json()
    assert [(slot["id"], slot["slot_index"]) for slot in slots] == [
        (s1["id"], 1),
        (s3["id"], 2),
    ]


def test_replace_slots_recalculates_slot_indexes_from_import_order(
    client: TestClient, device: dict, segment: dict
) -> None:
    r_segment2 = client.post(
        f"/api/v1/admin/fireflies/{device['id']}/segments",
        json={
            "channel_num": 2,
            "segment_num_in_channel": 1,
            "first_led_index": 1,
            "last_led_index": 150,
        },
    )
    assert r_segment2.status_code == 201, r_segment2.text

    client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "OLD",
            "segment_position": 1,
            "num_leds": 10,
        },
    )

    r_replace = client.put(
        f"{_slot_url(device['id'])}:replace",
        json={
            "slots": [
                {
                    "external_slot_id": "S-CH2",
                    "label": "Second channel",
                    "channel_num": 2,
                    "segment_num_in_channel": 1,
                    "segment_position": 1,
                    "num_leds": 12,
                },
                {
                    "external_slot_id": "S-CH1",
                    "label": "First channel",
                    "channel_num": 1,
                    "segment_num_in_channel": 1,
                    "segment_position": 1,
                    "num_leds": 10,
                },
            ]
        },
    )
    assert r_replace.status_code == 200, r_replace.text
    slots = r_replace.json()
    assert [(slot["external_slot_id"], slot["slot_index"]) for slot in slots] == [
        ("S-CH2", 1),
        ("S-CH1", 2),
    ]


def test_replace_slots_is_all_or_nothing_for_missing_segment(
    client: TestClient, device: dict, segment: dict
) -> None:
    original = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "KEEP",
            "segment_position": 1,
            "num_leds": 10,
        },
    ).json()

    r_replace = client.put(
        f"{_slot_url(device['id'])}:replace",
        json={
            "slots": [
                {
                    "external_slot_id": "BAD",
                    "label": None,
                    "channel_num": 99,
                    "segment_num_in_channel": 1,
                    "segment_position": 1,
                    "num_leds": 10,
                }
            ]
        },
    )
    assert r_replace.status_code == 422
    assert r_replace.json()["errorCode"] == "slot_import_invalid"

    r_list = client.get(_slot_url(device["id"]))
    assert r_list.status_code == 200
    assert [(slot["id"], slot["external_slot_id"]) for slot in r_list.json()] == [
        (original["id"], "KEEP"),
    ]


def test_duplicate_segment_position_rejected(
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
            "segment_position": 1,
            "num_leds": 10,
        },
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "slot_position_conflict"


def test_segment_position_is_not_a_starting_led_index(
    client: TestClient, device: dict, segment: dict
) -> None:
    r = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S145",
            "segment_position": 145,
            "num_leds": 10,
        },
    )
    assert r.status_code == 201, r.text


def test_total_slot_leds_must_fit_in_segment(
    client: TestClient, device: dict, segment: dict
) -> None:
    client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S1",
            "segment_position": 1,
            "num_leds": 145,
        },
    )
    r = client.post(
        _slot_url(device["id"]),
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S2",
            "segment_position": 2,
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
            "segment_position": 2,
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
            "segment_position": 2,
            "num_leds": 10,
        },
    )
    # Growing s1 beyond remaining segment capacity is rejected.
    r = client.put(
        f"{_slot_url(device['id'])}/{s1['id']}",
        json={"external_slot_id": s1["external_slot_id"], "label": None, "num_leds": 145},
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "slot_out_of_segment"


def test_unknown_slot_returns_404(client: TestClient, device: dict) -> None:
    r = client.get(f"{_slot_url(device['id'])}/9999")
    assert r.status_code == 404
    assert r.json()["errorCode"] == "slot_not_found"
