"""Tests for the JSON configuration loader (§13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from firefly_api.core.config import AppConfig, load_config


def _write_config(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_config_from_explicit_path(tmp_path: Path) -> None:
    cfg_path = _write_config(
        tmp_path / "settings.json",
        {
            "database": {"url": "sqlite:///./data/firefly.db"},
            "firefly": {
                "firefly_interface_version": "v01.04",
                "ackTimeoutMs": 5000,
                "ackMaxRetries": 2,
                "keepaliveDisconnectAfterSeconds": 60,
            },
            "events": {"retentionDays": 7},
            "frontend": {"staticFilesPath": "./frontend/dist"},
            "server": {"host": "127.0.0.1", "port": 8080},
            "logging": {"level": "DEBUG"},
        },
    )
    cfg = load_config(cfg_path)

    assert isinstance(cfg, AppConfig)
    assert cfg.database.url == "sqlite:///./data/firefly.db"
    assert cfg.firefly.firefly_interface_version == "v01.04"
    assert cfg.firefly.ack_timeout_ms == 5000
    assert cfg.firefly.ack_max_retries == 2
    assert cfg.firefly.keepalive_disconnect_after_seconds == 60
    assert cfg.events.retention_days == 7
    assert cfg.frontend.static_files_path == "./frontend/dist"
    assert cfg.server.host == "127.0.0.1"
    assert cfg.server.port == 8080
    assert cfg.logging.level == "DEBUG"


def test_load_config_missing_explicit_path(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as info:
        load_config(tmp_path / "does-not-exist.json")
    assert info.value.code == 2


def test_load_config_applies_firefly_defaults(tmp_path: Path) -> None:
    cfg_path = _write_config(
        tmp_path / "settings.json",
        {
            "database": {"url": "sqlite:///:memory:"},
            "firefly": {"firefly_interface_version": "v01.04"},
        },
    )
    cfg = load_config(cfg_path)

    assert cfg.firefly.ack_timeout_ms == 7000
    assert cfg.firefly.ack_max_retries == 3
    assert cfg.firefly.keepalive_disconnect_after_seconds == 300
    assert cfg.events.retention_days == 30
    assert cfg.frontend.static_files_path == "./frontend/dist"
    assert cfg.server.host == "0.0.0.0"
    assert cfg.server.port == 8000
