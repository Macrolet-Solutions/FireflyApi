"""Firefly MQTT topic builder and parser (§2, §6.2).

All outbound topics are produced through builder functions; inbound topics
are parsed by :func:`parse_inbound_topic`. There is one source of truth
for the topic strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Global subscription used by the actor registry (§5.1). The ``+`` wildcard
# matches the ``firefly_interface_version`` segment.
REGISTER_REQ_SUBSCRIPTION = "cmd/ptm/register-req/+"


class InboundTopicKind(str, Enum):
    REGISTER_REQUEST = "register_request"
    ACK = "ack"
    ERROR = "error"
    KEEPALIVE = "keepalive"


@dataclass(frozen=True)
class InboundTopic:
    """Result of parsing an inbound MQTT topic string.

    For ``REGISTER_REQUEST`` the ``device_name`` is ``None`` because the
    device identifier is carried in the JSON payload, not in the topic.
    """

    kind: InboundTopicKind
    version: str
    device_name: str | None = None


# Outbound builders ----------------------------------------------------------


def register_resp_topic(version: str, device_name: str) -> str:
    return f"ff/{version}/{device_name}/register-resp"


def init_slots_topic(version: str, device_name: str) -> str:
    return f"ff/{version}/{device_name}/init-slots"


def update_slot_state_topic(version: str, device_name: str) -> str:
    return f"ff/{version}/{device_name}/update-slot-state"


def update_all_slots_topic(version: str, device_name: str) -> str:
    return f"ff/{version}/{device_name}/update-all-slots"


def reset_topic(version: str, device_name: str) -> str:
    return f"ff/{version}/{device_name}/reset"


# Inbound builders (mainly for tests / device simulators) --------------------


def ack_topic(version: str, device_name: str) -> str:
    return f"ptm/{version}/{device_name}/ack"


def error_topic(version: str, device_name: str) -> str:
    return f"ptm/{version}/{device_name}/error"


def keepalive_topic(version: str, device_name: str) -> str:
    return f"ptm/{version}/{device_name}/keepalive"


def register_request_topic(version: str) -> str:
    return f"cmd/ptm/register-req/{version}"


# Subscriptions --------------------------------------------------------------


def device_subscriptions(version: str) -> list[str]:
    """Per-version subscription patterns covering ack/error/keepalive."""
    return [
        f"ptm/{version}/+/ack",
        f"ptm/{version}/+/error",
        f"ptm/{version}/+/keepalive",
    ]


# Parser ---------------------------------------------------------------------


def parse_inbound_topic(topic: str) -> InboundTopic | None:
    """Parse an inbound MQTT topic into a structured ``InboundTopic``.

    Returns ``None`` for topics that don't match any known pattern so the
    caller can log and ignore them.
    """
    parts = topic.split("/")

    # cmd/ptm/register-req/{version}
    if (
        len(parts) == 4
        and parts[0] == "cmd"
        and parts[1] == "ptm"
        and parts[2] == "register-req"
    ):
        return InboundTopic(
            kind=InboundTopicKind.REGISTER_REQUEST,
            version=parts[3],
            device_name=None,
        )

    # ptm/{version}/{deviceName}/{ack|error|keepalive}
    if len(parts) == 4 and parts[0] == "ptm":
        version, device_name, leaf = parts[1], parts[2], parts[3]
        if leaf == "ack":
            return InboundTopic(InboundTopicKind.ACK, version, device_name)
        if leaf == "error":
            return InboundTopic(InboundTopicKind.ERROR, version, device_name)
        if leaf == "keepalive":
            return InboundTopic(InboundTopicKind.KEEPALIVE, version, device_name)

    return None
