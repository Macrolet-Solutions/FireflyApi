"""Per-device actor system (§5).

Re-exports the registry and device-actor classes plus the message and
configuration dataclasses for callers (the service layer, tests).
"""

from firefly_api.firefly.actors.device import (
    ActorStatus,
    CommandFailure,
    CommandOutcome,
    CommandSuccess,
    DeviceConfig,
    FireflyDeviceActor,
    PendingCommand,
    RuntimeSettings,
    StateMachine,
)
from firefly_api.firefly.actors.registry import ActorRegistry

__all__ = [
    "ActorRegistry",
    "ActorStatus",
    "CommandFailure",
    "CommandOutcome",
    "CommandSuccess",
    "DeviceConfig",
    "FireflyDeviceActor",
    "PendingCommand",
    "RuntimeSettings",
    "StateMachine",
]
