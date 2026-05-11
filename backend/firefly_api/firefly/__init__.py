"""Firefly device integration layer (§4 module layout).

Contains:

- :mod:`firefly_api.firefly.protocol` — MQTT topic builder, Pydantic
  payload models, protocol constants. Pure data; no IO.
- :mod:`firefly_api.firefly.mqtt` — paho-based MQTT client wrapper.
- :mod:`firefly_api.firefly.actors` — actor registry and per-device
  Pykka actor with the §5 state machine.
- :mod:`firefly_api.firefly.service` — high-level operations called by
  the HTTP layer (Phase 3).
"""
