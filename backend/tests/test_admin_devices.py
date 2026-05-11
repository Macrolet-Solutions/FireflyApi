"""HTTP tests for ``/api/v1/admin/fireflies`` (§7.2, §9)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_empty(client: TestClient) -> None:
    r = client.get("/api/v1/admin/fireflies")
    assert r.status_code == 200
    assert r.json() == []


def test_create_requires_existing_broker(client: TestClient) -> None:
    r = client.post(
        "/api/v1/admin/fireflies",
        json={"name": "FF01", "mqtt_broker_id": 999},
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "invalid_mqtt_broker_id"


def test_create_roundtrip(client: TestClient, broker: dict) -> None:
    r = client.post(
        "/api/v1/admin/fireflies",
        json={
            "name": "FF01",
            "display_name": "Aisle 1",
            "mqtt_broker_id": broker["id"],
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "FF01"
    assert body["display_name"] == "Aisle 1"
    assert body["mqtt_broker_id"] == broker["id"]


def test_duplicate_name_returns_409(client: TestClient, device: dict) -> None:
    r = client.post(
        "/api/v1/admin/fireflies",
        json={"name": device["name"], "mqtt_broker_id": device["mqtt_broker_id"]},
    )
    assert r.status_code == 409
    assert r.json()["errorCode"] == "device_name_conflict"


def test_update_changes_display_name(client: TestClient, device: dict) -> None:
    r = client.put(
        f"/api/v1/admin/fireflies/{device['id']}",
        json={
            "name": device["name"],
            "display_name": "Renamed",
            "mqtt_broker_id": device["mqtt_broker_id"],
        },
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Renamed"


def test_delete_cascades_in_db(client: TestClient, device: dict) -> None:
    r = client.delete(f"/api/v1/admin/fireflies/{device['id']}")
    assert r.status_code == 204
    r = client.get(f"/api/v1/admin/fireflies/{device['id']}")
    assert r.status_code == 404


def test_get_unknown_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/admin/fireflies/9999")
    assert r.status_code == 404
    assert r.json()["errorCode"] == "device_not_found"
