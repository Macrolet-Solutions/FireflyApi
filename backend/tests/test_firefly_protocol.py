"""Tests for :mod:`firefly_api.firefly.protocol` (§6).

Covers topic builders/parsers, payload alias mapping, and the pattern enum.
"""

from __future__ import annotations

import json

import pytest

from firefly_api.firefly.protocol import (
    AckIn,
    ErrorIn,
    InboundTopicKind,
    InitSlotsOut,
    InitSlotsSlot,
    KeepaliveIn,
    LedPattern,
    LedStateOut,
    RegistrationRequestIn,
    RegistrationResponseOut,
    SegmentOut,
    UpdateAllSlotsOut,
    UpdateSlotStateOut,
    UpdateSlotStateSlot,
    ack_topic,
    device_subscriptions,
    error_topic,
    init_slots_topic,
    keepalive_topic,
    parse_inbound_topic,
    pattern_from_public_name,
    public_name_for_pattern,
    register_resp_topic,
    reset_topic,
    update_all_slots_topic,
    update_slot_state_topic,
)
from firefly_api.firefly.protocol.topics import register_request_topic


VERSION = "v01.04"
DEVICE = "FF01"


# ---------------------------------------------------------------- topics ----


def test_outbound_topic_strings() -> None:
    assert register_resp_topic(VERSION, DEVICE) == "ff/v01.04/FF01/register-resp"
    assert init_slots_topic(VERSION, DEVICE) == "ff/v01.04/FF01/init-slots"
    assert (
        update_slot_state_topic(VERSION, DEVICE) == "ff/v01.04/FF01/update-slot-state"
    )
    assert update_all_slots_topic(VERSION, DEVICE) == "ff/v01.04/FF01/update-all-slots"
    assert reset_topic(VERSION, DEVICE) == "ff/v01.04/FF01/reset"


def test_inbound_topic_strings() -> None:
    assert ack_topic(VERSION, DEVICE) == "ptm/v01.04/FF01/ack"
    assert error_topic(VERSION, DEVICE) == "ptm/v01.04/FF01/error"
    assert keepalive_topic(VERSION, DEVICE) == "ptm/v01.04/FF01/keepalive"


def test_device_subscriptions() -> None:
    subs = device_subscriptions(VERSION)
    assert set(subs) == {
        "ptm/v01.04/+/ack",
        "ptm/v01.04/+/error",
        "ptm/v01.04/+/keepalive",
    }


def test_parse_register_request_topic() -> None:
    parsed = parse_inbound_topic(register_request_topic(VERSION))
    assert parsed is not None
    assert parsed.kind is InboundTopicKind.REGISTER_REQUEST
    assert parsed.version == VERSION
    assert parsed.device_name is None


@pytest.mark.parametrize(
    "topic_fn,kind",
    [
        (ack_topic, InboundTopicKind.ACK),
        (error_topic, InboundTopicKind.ERROR),
        (keepalive_topic, InboundTopicKind.KEEPALIVE),
    ],
)
def test_parse_inbound_device_topics(topic_fn, kind) -> None:  # noqa: ANN001
    parsed = parse_inbound_topic(topic_fn(VERSION, DEVICE))
    assert parsed is not None
    assert parsed.kind is kind
    assert parsed.version == VERSION
    assert parsed.device_name == DEVICE


def test_parse_unknown_topic_returns_none() -> None:
    assert parse_inbound_topic("random/garbage") is None
    assert parse_inbound_topic("ff/v01.04/FF01/init-slots") is None  # outbound topic
    assert parse_inbound_topic("ptm/v01.04/FF01/unknown") is None


# --------------------------------------------------------------- payloads ----


def test_registration_request_parses_kebab_aliases() -> None:
    raw = {
        "firmware-version": "1.2.3",
        "device-id": "FF01",
        "device-mac": "AABBCCDDEEFF",
        # An extra field the firmware might add later must not blow up parsing.
        "future-field": True,
    }
    req = RegistrationRequestIn.model_validate(raw)
    assert req.firmware_version == "1.2.3"
    assert req.device_id == "FF01"
    assert req.device_mac == "AABBCCDDEEFF"


def test_ack_payload_round_trip() -> None:
    raw = '{"event-id": "67c7f3a1-1c19-4b4e-babd-a31128707e6f"}'
    ack = AckIn.model_validate_json(raw)
    assert ack.event_id == "67c7f3a1-1c19-4b4e-babd-a31128707e6f"


def test_error_payload_round_trip() -> None:
    raw = {
        "event-id": "abc",
        "error-code": "TASK_ID_MISMATCH_UPDATING_CELLS",
        "error-descr": "wrong task",
    }
    err = ErrorIn.model_validate(raw)
    assert err.event_id == "abc"
    assert err.error_code == "TASK_ID_MISMATCH_UPDATING_CELLS"
    assert err.error_descr == "wrong task"


def test_error_payload_accepts_numeric_error_code() -> None:
    raw = {
        "event-id": "abc",
        "error-code": 1,
        "error-descr": "numeric firmware code",
    }
    err = ErrorIn.model_validate(raw)
    assert err.error_code == "1"
    assert err.error_descr == "numeric firmware code"


def test_keepalive_optional_fields_default_to_none() -> None:
    ka = KeepaliveIn.model_validate({})
    assert ka.free_memory is None
    assert ka.battery is None


def test_registration_response_serializes_with_wire_aliases() -> None:
    resp = RegistrationResponseOut(
        is_error=False,
        event_id="evt",
        device_type="FireflyController",
        segments=[SegmentOut(channel=1, ch_segm=1, first_led_inx=1, last_led_inx=150)],
        states=[
            LedStateOut(
                name="NEEDS-ATTENTION",
                rgb="0xFF8000",
                color1_on_ms=500,
            )
        ],
    )
    wire = json.loads(resp.model_dump_json(by_alias=True))
    assert wire["is-error"] is False
    assert wire["error-descr"] == ""
    assert wire["event-id"] == "evt"
    assert wire["device-type"] == "FireflyController"
    assert wire["segments"][0]["ch-segm"] == 1
    assert wire["segments"][0]["first-led-inx"] == 1
    assert wire["segments"][0]["last-led-inx"] == 150
    assert wire["states"][0]["name"] == "NEEDS-ATTENTION"
    assert wire["states"][0]["color1-on-ms"] == 500
    assert wire["states"][0]["num-rep"] == 0


def test_init_slots_serializes_with_wire_aliases() -> None:
    msg = InitSlotsOut(
        event_id="evt",
        task_id="task",
        num_slots=2,
        slots=[
            InitSlotsSlot(
                slot_inx=1, channel=1, ch_segm=1, pos_in_segm=1, num_leds=10
            ),
            InitSlotsSlot(
                slot_inx=2, channel=1, ch_segm=1, pos_in_segm=11, num_leds=10
            ),
        ],
    )
    wire = json.loads(msg.model_dump_json(by_alias=True))
    assert wire["event-id"] == "evt"
    assert wire["task-id"] == "task"
    assert wire["num-slots"] == 2
    assert wire["slots"][0] == {
        "slot-inx": 1,
        "channel": 1,
        "ch-segm": 1,
        "pos-in-segm": 1,
        "num-leds": 10,
    }


def test_update_slot_state_serializes_with_wire_aliases() -> None:
    msg = UpdateSlotStateOut(
        event_id="evt",
        task_id="task",
        slots=[
            UpdateSlotStateSlot(
                slot_inx=1,
                to_state="NEEDS-ATTENTION",
                pattern=int(LedPattern.SLOT_ENDS),
                pattern_value=10,
            )
        ],
    )
    wire = json.loads(msg.model_dump_json(by_alias=True))
    assert wire["slots"][0] == {
        "slot-inx": 1,
        "to-state": "NEEDS-ATTENTION",
        "pattern": 1,
        "pattern-value": 10,
    }


def test_update_all_slots_serializes_with_wire_aliases() -> None:
    msg = UpdateAllSlotsOut(
        event_id="evt",
        task_id="task",
        to_state="OFF",
        pattern=0,
        pattern_value=0,
    )
    wire = json.loads(msg.model_dump_json(by_alias=True))
    assert wire == {
        "event-id": "evt",
        "task-id": "task",
        "to-state": "OFF",
        "pattern": 0,
        "pattern-value": 0,
    }


# ---------------------------------------------------------------- patterns ----


def test_pattern_public_names_round_trip() -> None:
    for pattern in LedPattern:
        public = public_name_for_pattern(int(pattern))
        assert pattern_from_public_name(public) is pattern


def test_pattern_from_public_name_rejects_unknown() -> None:
    with pytest.raises(Exception) as info:
        pattern_from_public_name("bogus")
    assert "invalid_pattern" in str(info.value.__class__.__name__) or hasattr(
        info.value, "error_code"
    )


def test_public_name_for_invalid_integer_rejected() -> None:
    with pytest.raises(Exception):
        public_name_for_pattern(99)
