"""HTTP tests for ``/api/v1/admin/led-states`` (§7.5)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_and_list(client: TestClient) -> None:
    r = client.post(
        "/api/v1/admin/led-states",
        json={
            "name": "NEEDS-ATTENTION",
            "rgb": "0xFF8000",
            "color1_on_ms": 500,
            "color1_fade_up_ms": 100,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "NEEDS-ATTENTION"
    assert body["rgb"] == "0xFF8000"

    r = client.get("/api/v1/admin/led-states")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_rgb_format_enforced(client: TestClient) -> None:
    r = client.post(
        "/api/v1/admin/led-states",
        json={"name": "BAD", "rgb": "FF8000"},
    )
    assert r.status_code == 422


def test_duplicate_name_returns_409(client: TestClient, led_state: dict) -> None:
    r = client.post(
        "/api/v1/admin/led-states",
        json={"name": led_state["name"], "rgb": "0x000000"},
    )
    assert r.status_code == 409
    assert r.json()["errorCode"] == "led_state_name_conflict"


def test_delete_with_preset_returns_409(client: TestClient, led_state: dict) -> None:
    r = client.post(
        "/api/v1/admin/command-presets",
        json={
            "name": "warning",
            "led_state_id": led_state["id"],
            "pattern": 1,
            "pattern_value": 10,
        },
    )
    assert r.status_code == 201, r.text

    r = client.delete(f"/api/v1/admin/led-states/{led_state['id']}")
    assert r.status_code == 409
    assert r.json()["errorCode"] == "led_state_in_use"


def test_unknown_led_state_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/admin/led-states/9999")
    assert r.status_code == 404
    assert r.json()["errorCode"] == "led_state_not_found"
