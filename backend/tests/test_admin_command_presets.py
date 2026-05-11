"""HTTP tests for ``/api/v1/admin/command-presets`` (§7.6)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_and_list(client: TestClient, led_state: dict) -> None:
    r = client.post(
        "/api/v1/admin/command-presets",
        json={
            "name": "warning",
            "led_state_id": led_state["id"],
            "pattern": 1,
            "pattern_value": 10,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "warning"
    assert body["pattern"] == 1
    assert body["pattern_value"] == 10


def test_pattern_out_of_range_rejected(client: TestClient, led_state: dict) -> None:
    r = client.post(
        "/api/v1/admin/command-presets",
        json={
            "name": "bad",
            "led_state_id": led_state["id"],
            "pattern": 7,
        },
    )
    assert r.status_code == 422


def test_unknown_led_state_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/v1/admin/command-presets",
        json={
            "name": "warning",
            "led_state_id": 9999,
            "pattern": 0,
        },
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "invalid_led_state_id"


def test_duplicate_name_returns_409(client: TestClient, led_state: dict) -> None:
    payload = {
        "name": "warning",
        "led_state_id": led_state["id"],
        "pattern": 0,
    }
    client.post("/api/v1/admin/command-presets", json=payload)
    r = client.post("/api/v1/admin/command-presets", json=payload)
    assert r.status_code == 409
    assert r.json()["errorCode"] == "command_preset_name_conflict"


def test_delete_succeeds(client: TestClient, led_state: dict) -> None:
    created = client.post(
        "/api/v1/admin/command-presets",
        json={
            "name": "warning",
            "led_state_id": led_state["id"],
            "pattern": 0,
        },
    ).json()
    r = client.delete(f"/api/v1/admin/command-presets/{created['id']}")
    assert r.status_code == 204


def test_unknown_preset_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/admin/command-presets/9999")
    assert r.status_code == 404
    assert r.json()["errorCode"] == "command_preset_not_found"
