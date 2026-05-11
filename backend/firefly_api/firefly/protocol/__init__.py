"""Firefly MQTT protocol primitives (§6).

Re-exports the public surface of the topic builder, payload models, and
protocol constants so callers can ``from firefly_api.firefly.protocol
import ...`` without reaching into submodules.
"""

from firefly_api.firefly.protocol.patterns import (
    PATTERN_FIRMWARE_NAMES,
    PATTERN_PUBLIC_NAMES,
    LedPattern,
    pattern_from_public_name,
    public_name_for_pattern,
)
from firefly_api.firefly.protocol.payloads import (
    AckIn,
    ErrorIn,
    InitSlotsOut,
    InitSlotsSlot,
    KeepaliveIn,
    LedStateOut,
    RegistrationRequestIn,
    RegistrationResponseOut,
    SegmentOut,
    UpdateAllSlotsOut,
    UpdateSlotStateOut,
    UpdateSlotStateSlot,
)
from firefly_api.firefly.protocol.topics import (
    REGISTER_REQ_SUBSCRIPTION,
    InboundTopic,
    InboundTopicKind,
    ack_topic,
    device_subscriptions,
    error_topic,
    init_slots_topic,
    keepalive_topic,
    parse_inbound_topic,
    register_resp_topic,
    reset_topic,
    update_all_slots_topic,
    update_slot_state_topic,
)

ERROR_NO_TASK_ID = "NO_TASK_ID_WHEN_UPDATING_CELLS"
ERROR_TASK_ID_MISMATCH = "TASK_ID_MISMATCH_UPDATING_CELLS"

TASK_ID_RECOVERY_ERROR_CODES = frozenset({ERROR_NO_TASK_ID, ERROR_TASK_ID_MISMATCH})

__all__ = [
    "AckIn",
    "ERROR_NO_TASK_ID",
    "ERROR_TASK_ID_MISMATCH",
    "ErrorIn",
    "InboundTopic",
    "InboundTopicKind",
    "InitSlotsOut",
    "InitSlotsSlot",
    "KeepaliveIn",
    "LedPattern",
    "LedStateOut",
    "PATTERN_FIRMWARE_NAMES",
    "PATTERN_PUBLIC_NAMES",
    "REGISTER_REQ_SUBSCRIPTION",
    "RegistrationRequestIn",
    "RegistrationResponseOut",
    "SegmentOut",
    "TASK_ID_RECOVERY_ERROR_CODES",
    "UpdateAllSlotsOut",
    "UpdateSlotStateOut",
    "UpdateSlotStateSlot",
    "ack_topic",
    "device_subscriptions",
    "error_topic",
    "init_slots_topic",
    "keepalive_topic",
    "parse_inbound_topic",
    "pattern_from_public_name",
    "public_name_for_pattern",
    "register_resp_topic",
    "reset_topic",
    "update_all_slots_topic",
    "update_slot_state_topic",
]
