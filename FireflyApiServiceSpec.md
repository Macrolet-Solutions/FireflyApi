# Firefly API Service Specification

## 1. Purpose

Firefly API Service is a middleware and configuration platform for Macrolet Firefly devices. A Firefly device is proprietary Macrolet hardware that controls up to two LED strips and communicates with higher-level software through MQTT. The service will hide the low-level MQTT protocol, device registration, ACK/error handling, task identity, slot initialization, and connection state management behind a web UI and a higher-level HTTP API.

The main consumers are:

- Integrators and end users who need a browser interface to configure Firefly devices, LED segments, slots, and operational state mappings.
- External systems, typically a WCS, WES, sorter controller, picking-cart controller, or light-guided workflow application, that need simple HTTP endpoints to light slots without knowing the Firefly MQTT protocol.

The application will consist of:

- A Python backend using FastAPI.
- SQLAlchemy for database access.
- Alembic for schema migrations.
- A lightweight local database by default. SQLite is recommended for a true local file-based database
- A React frontend served by the FastAPI backend.
- An actor-based Firefly runtime using Pykka to mirror the Akka.NET design used in the existing Macrolet EndOfLine integration.
- An MQTT client layer for the Firefly protocol.

## 2. Reference Implementation Findings

The existing implementation in `Macrolet_EndOfLine` is part of a complete WCS/EOL sorter application. The reusable portion for this service is the low-level Firefly integration implemented mainly in `FireFlySorterActor.fs`, supported by MQTT topic definitions, payload models, database queries, and the registration processor.

Important behavior to preserve:

- One actor instance manages one configured Firefly device.
- Devices communicate using versioned MQTT topics.
- Device registration is initiated by the Firefly device over MQTT.
- The server accepts or rejects registration based on configured device name and MQTT protocol version.
- Registration response includes static LED strip segment definitions and named LED states.
- After registration, the server initializes slots with a generated `task-id`.
- Slot updates are serialized per device through `event-id` correlation and ACK/error handling.
- If a command does not receive an ACK within the timeout, the device is treated as disconnected for that command path.
- Device errors such as missing or mismatched task ID cause reinitialization of slots.
- Keepalive messages update device liveness.
- Slot configuration and segment configuration are persisted in the database.
- Runtime active state is actor-owned: current task ID, active/focused slot, occupied slots, and connection state.

Reference MQTT topics:

```text
From device:
cmd/ptm/register-req/+
cmd/ptm/register-req/{mqttVersion}
ptm/{mqttVersion}/{deviceName}/ack
ptm/{mqttVersion}/{deviceName}/error
ptm/{mqttVersion}/{deviceName}/keepalive

To device:
ff/{mqttVersion}/{deviceName}/register-resp
ff/{mqttVersion}/{deviceName}/init-slots
ff/{mqttVersion}/{deviceName}/extend-slots
ff/{mqttVersion}/{deviceName}/update-slot-state
ff/{mqttVersion}/{deviceName}/update-all-slots
ff/{mqttVersion}/{deviceName}/release-slots
ff/{mqttVersion}/{deviceName}/reset
```

Reference MQTT payload concepts:

- Registration request: firmware version, device ID/name, MAC address.
- Registration response: error flag, error description, event ID, device type, LED segments, named LED states.
- ACK: event ID.
- Error: event ID, error code, error description.
- Keepalive: free memory and battery fields.
- Init slots: event ID, task ID, number of slots, slot definitions.
- Update slot state: event ID, task ID, list of slot state changes.

## 3. Product Scope

### 3.1 In Scope

- Configure MQTT broker connection settings.
- Configure Firefly devices known to this service.
- Configure each device's LED strip segments.
- Configure logical slots mapped to device LED segments.
- Configure reusable LED states and high-level commands such as off, solid color, blink, pulse, and attention/focus patterns.
- Detect device registration, online/offline state, keepalive, firmware version, MAC address, last registration time, and last keepalive time.
- Initialize devices after registration or service startup.
- Expose admin APIs used by the React frontend.
- Expose public integration APIs used by external systems.
- Provide a frontend for device management, slot/segment editing, live device status, and manual slot testing.
- Persist configuration and recent runtime metadata.
- Maintain per-device actor state for reliable command serialization and ACK/error handling.

### 3.2 Out of Scope

- Full WCS behavior such as container assignment, sort destination calculation, PDA messaging, operator station workflows, and shipping-sorter business rules.
- Multi-tenant authorization unless explicitly required later.
- Historical analytics beyond basic command/event logs.
- Direct firmware update management.
- Direct LED strip electrical diagnostics.

## 4. System Architecture

```text
External WCS / client apps
				|
				| HTTP public API
				v
FastAPI backend ------------- React frontend
				|
				| service layer
				v
Firefly actor registry
				|
				| per-device actor mailbox
				v
Firefly device actor(s)
				|
				| MQTT publish/subscribe
				v
MQTT broker
				|
				v
Firefly hardware devices

FastAPI backend <---- SQLAlchemy/Alembic ----> Local database
```

Backend modules should be organized around these responsibilities:

- `api.admin`: frontend-facing management endpoints.
- `api.public`: external integrator endpoints.
- `core.config`: application settings, MQTT broker settings, database URL, protocol version, timeouts.
- `db.models`: SQLAlchemy ORM models.
- `db.repositories`: database persistence operations.
- `firefly.protocol`: MQTT topics, payload schemas, protocol constants, serializers.
- `firefly.mqtt`: MQTT client wrapper and subscription lifecycle.
- `firefly.actors`: actor registry, device actor, actor messages, retry/timeout handling.
- `firefly.service`: high-level operations used by APIs.
- `frontend`: built React app served as static files by FastAPI.

## 5. Firefly Runtime Model

### 5.1 Actor Registry

The actor registry owns all active Firefly device actors. On backend startup it loads enabled devices from the database and starts one actor per device. It also owns the global registration-request subscription:

```text
cmd/ptm/register-req/+
```

When a registration request arrives, the registry parses the device ID/name and forwards the message to the matching device actor. If the device is unknown, the service should log the event and optionally publish a registration error response if enough protocol information is available.

### 5.2 Device Actor State

Each actor should keep these runtime fields:

- `device_id`: internal database ID.
- `device_name`: Firefly MQTT device identifier.
- `status`: unknown, online, offline, register_error.
- `mqtt_version`: configured server protocol version.
- `current_task_id`: task ID accepted by the device after slot initialization.
- `slots`: ordered slot configuration for the device.
- `active_slot`: optional slot currently highlighted/focused.
- `occupied_slots`: optional set of occupied logical slots if the service is used in workflows that need persistent occupancy.
- `pending_command`: optional command waiting for ACK, including event ID, deadline, retry count, and caller correlation.
- `last_keepalive_at`, `registered_at`, `mac_address`, `firmware_version`.

### 5.3 Device Actor States

The Python actor should preserve the state machine shape from the reference implementation:

- `reset`: actor has no known initialized device session.
- `registering`: actor received registration request and is waiting for ACK to registration response.
- `initializing_slots`: actor sent `init-slots` and is waiting for ACK.
- `updating_slots`: actor sent `update-slot-state` or `update-all-slots` and is waiting for ACK.
- `active`: actor has initialized slots and can accept commands.
- `offline`: actor cannot execute commands until registration or keepalive allows reinitialization.

Only one MQTT command that requires ACK should be in flight per device actor. Additional API requests should either be queued by the actor mailbox or rejected with a clear conflict response, depending on the final desired behavior. For version 1, queueing through the actor mailbox is recommended.

### 5.4 ACK, Error, and Timeout Handling

Every MQTT command requiring confirmation must include a generated UUID `event-id`. The actor starts a timeout when publishing. The timeout should default to 7000 ms, matching the reference behavior, and be configurable.

When an ACK arrives:

- If `event-id` matches the pending command, cancel the timeout and transition to the next state.
- If `event-id` does not match, log a warning and keep waiting.

When an error arrives:

- If `event-id` matches, cancel the timeout and complete the command with a failure.
- If the error code is `NO_TASK_ID_WHEN_UPDATING_CELLS` or `TASK_ID_MISMATCH_UPDATING_CELLS`, reinitialize slots.
- Otherwise mark the device offline or disconnected according to the command state.

When a timeout expires:

- Complete the command with a timeout error.
- Mark the device offline/disconnected.
- Keep the actor alive so it can recover on registration or keepalive.

## 6. MQTT Protocol

### 6.1 Protocol Version

The service must define a configured Firefly MQTT protocol version, for example `1`. A registration request for a different version must be rejected with a registration error response.

### 6.2 Topic Builder

All MQTT topics must be produced through a single topic builder module to avoid string duplication. Topic names must match the protocol listed in section 2 unless a newer firmware protocol is confirmed.

### 6.3 Payload Schemas

Use Pydantic models for all MQTT payloads, with aliases matching Firefly JSON field names.

Example registration request:

```json
{
	"firmware-version": "1.2.3",
	"device-id": "FF01",
	"device-mac": "AABBCCDDEEFF"
}
```

Example registration response:

```json
{
	"is-error": false,
	"error-descr": "",
	"event-id": "67c7f3a1-1c19-4b4e-babd-a31128707e6f",
	"device-type": "FireflyController",
	"segments": [
		{
			"channel": 1,
			"ch-segm": 1,
			"first-led-inx": 0,
			"last-led-inx": 149
		}
	],
	"states": [
		{
			"name": "OFF",
			"rgb": "0x000000",
			"color1-on-ms": 0,
			"color1-fade-up-ms": 0,
			"color1-fade-down-ms": 0,
			"repeat-after-ms": 0,
			"num-rep": 0
		}
	]
}
```

Example init slots payload:

```json
{
	"event-id": "67c7f3a1-1c19-4b4e-babd-a31128707e6f",
	"task-id": "a9d9e5f5-21ce-4afb-a26e-5dd5f4e9db5c",
	"num-slots": 2,
	"slots": [
		{
			"slot-inx": 1,
			"channel": 1,
			"ch-segm": 1,
			"pos-in-segm": 1,
			"num-leds": 10
		}
	]
}
```

Example update slot state payload:

```json
{
	"event-id": "67c7f3a1-1c19-4b4e-babd-a31128707e6f",
	"task-id": "a9d9e5f5-21ce-4afb-a26e-5dd5f4e9db5c",
	"slots": [
		{
			"slot-inx": 1,
			"to-state": "FOCUS-POSITION",
			"pattern": 0,
			"pattern-value": 0
		}
	]
}
```

### 6.4 Slot LED Patterns

Slot LED patterns are not configurable LED states. They are firmware-defined rendering modes that tell the Firefly device which part of a configured slot should receive the target LED state. The service should expose them as a fixed enum unless a future firmware version adds more values.

The service should support these pattern values:

- `0`: full slot.
- `1`: slot ends. Inferred meaning: apply the state only to the LEDs at the beginning and end of the slot, leaving the middle off or unchanged according to firmware behavior.
- `2`: slot without ends. Inferred meaning: apply the state to the interior LEDs of the slot while excluding the beginning and end LEDs.
- `3`: subsegments only. Inferred meaning: apply the state only to a specific subsegment inside the slot, using `pattern-value` as the subsegment selector.

LED states define the color and timing behavior, such as solid, blink, fade, or pulse. Patterns define where that state is applied inside the slot. For example, the same `NEEDS-ATTENTION` state can be applied to the full slot or only to the slot ends.

The exact LED counts used by `slot_ends`, `slot_no_ends`, and `subsegments` appear to be firmware behavior rather than application behavior. This should be confirmed with Firefly firmware documentation or a hardware test before exposing detailed descriptions in end-user documentation.

### 6.5 LED States

The system should not seed any default LED states. The states from the existing EndOfLine sorter integration are specific to that sorter use case and should not be treated as product defaults for this service.

LED states must be configured by an administrator or integrator before a Firefly device can be registered successfully. During device registration, the service returns the currently configured states for that installation. If no states are configured, the service should either reject registration with a clear configuration error or keep the device offline until the configuration is completed.

The frontend should provide a blank initial LED state catalog and allow users to create, edit, duplicate, and delete states. The UI may offer optional examples or templates in documentation, but those examples must not be inserted into the database automatically.

## 7. Database Model

The database must persist configuration and enough runtime metadata for recovery after service restart. SQLAlchemy models should use normal integer primary keys and database-level uniqueness constraints.

Recommended tables:

### 7.1 `mqtt_brokers`

- `id`
- `name`
- `host`
- `port`
- `username`
- `password_secret_ref` or encrypted password field
- `use_tls`
- `client_id`
- `enabled`
- `created_at`
- `updated_at`

Version 1 can support one active broker, but the schema may allow multiple broker profiles.

### 7.2 `firefly_devices`

- `id`
- `name`: unique Firefly MQTT device identifier, such as `FF01`.
- `display_name`
- `description`
- `status`: unknown, online, offline, register_error.
- `enabled`
- `mqtt_broker_id`
- `mac_address`
- `firmware_version`
- `registered_at`
- `last_keepalive_at`
- `current_task_id`
- `last_error_code`
- `last_error_description`
- `created_at`
- `updated_at`

### 7.3 `firefly_segments`

- `id`
- `device_id`
- `channel_num`: physical LED channel, normally 1 or 2.
- `segment_num_in_channel`
- `first_led_index`
- `last_led_index`
- `created_at`
- `updated_at`

This maps directly to the reference `FireFlySegment` configuration returned during registration.

### 7.4 `firefly_slots`

- `id`
- `device_id`
- `segment_id`
- `slot_index`: 1-based index sent to the Firefly device.
- `external_slot_id`: optional business/integrator slot identifier.
- `label`
- `segment_position`
- `num_leds`
- `enabled`
- `created_at`
- `updated_at`

Slot ordering must be deterministic. The reference implementation orders by channel, segment number, and segment position, then maps to 1-based `slot-inx`. This service should store `slot_index` explicitly and validate uniqueness per device.

### 7.5 `firefly_led_states`

- `id`
- `name`: unique state name.
- `rgb`: string in `0xRRGGBB` format.
- `color1_on_ms`
- `color1_fade_up_ms`
- `color1_fade_down_ms`
- `repeat_after_ms`
- `num_repetitions`
- `is_system`
- `created_at`
- `updated_at`

### 7.6 `firefly_command_presets`

- `id`
- `name`: off, solid, blink, pulse, focus, occupied, warning, success, error, custom.
- `led_state_id`
- `pattern`
- `pattern_value`
- `created_at`
- `updated_at`

This table maps high-level API actions to low-level device state and pattern values.

### 7.7 `firefly_slot_runtime_states`

- `id`
- `device_id`
- `slot_id`
- `last_state_name`
- `last_pattern`
- `last_pattern_value`
- `is_occupied`
- `is_active`
- `last_updated_at`

This table is useful for frontend display and service restart recovery. The actor remains the source of truth while running.

### 7.8 `firefly_events`

- `id`
- `device_id`
- `event_id`
- `event_type`: registration, init_slots, update_slot_state, update_all_slots, reset, ack, error, timeout, keepalive.
- `status`: pending, acked, failed, timed_out.
- `request_payload_json`
- `response_payload_json`
- `error_code`
- `error_description`
- `created_at`
- `completed_at`

This table should be bounded by retention settings so it does not grow indefinitely.

## 8. Public Integration API

Public endpoints are intended for external applications that want to control Firefly devices without knowing MQTT details. They should be stable, documented through OpenAPI, and versioned under `/api/v1/public`.

### 8.1 Update Firefly Slots

```http
POST /api/v1/public/fireflies/{deviceName}/slots:update
```

Equivalent friendly operation name: `updateFireflySlots`.

Request:

```json
{
	"slots": [
		{
			"slotIndex": 1,
			"stateName": "PICK-READY",
			"pattern": "full",
			"patternValue": 0
		},
		{
			"slotIndex": 2,
			"stateName": "NEEDS-ATTENTION",
			"pattern": "slot_ends",
			"patternValue": 10
		},
		{
			"slotIndex": 3,
			"stateName": "OFF",
			"pattern": "full",
			"patternValue": 0
		}
	],
	"clientRequestId": "optional-client-correlation-id",
	"timeoutMs": 7000
}
```

Response:

```json
{
	"deviceName": "FF01",
	"status": "updated",
	"eventId": "67c7f3a1-1c19-4b4e-babd-a31128707e6f",
	"clientRequestId": "optional-client-correlation-id"
}
```

The preferred version 1 contract is explicit and close to the Firefly device model: callers provide a `slotIndex`, a configured `stateName`, and optional `pattern` and `patternValue` information. The service validates that the state exists in `firefly_led_states`, validates that the pattern is one of the fixed firmware-supported pattern values, translates the request into Firefly `to-state`, `pattern`, and `pattern-value` fields, and sends one MQTT `update-slot-state` command to the device actor.

If `pattern` is omitted, the service should default it to `full`. If `patternValue` is omitted, the service should default it to `0`. For patterns where firmware gives `pattern-value` a special meaning, callers may provide a non-zero `patternValue`.

The `stateName` must already be configured and must have been sent to the device during registration. For example, turning a slot off is not a built-in command unless the installation has configured an LED state such as `OFF` with RGB `0x000000` and the device has registered with that state.

Supported pattern values for the public API:

- `full`: maps to Firefly pattern `0`.
- `slot_ends`: maps to Firefly pattern `1`.
- `slot_no_ends`: maps to Firefly pattern `2`.
- `subsegments`: maps to Firefly pattern `3` and requires `patternValue`.

Optional higher-level presets may be added as a convenience layer, but they should resolve to the same explicit fields before reaching the actor. For example, a preset named `warning` may resolve to `stateName: "NEEDS-ATTENTION"`, `pattern: "slot_ends"`, and a specific `patternValue`. Presets should not replace direct state-based control in the core public API.

### 8.2 Update All Slots

```http
POST /api/v1/public/fireflies/{deviceName}/slots:update-all
```

Request:

```json
{
	"action": "off",
	"presetName": null,
	"clientRequestId": "optional-client-correlation-id",
	"timeoutMs": 7000
}
```

### 8.3 Reset Device

```http
POST /api/v1/public/fireflies/{deviceName}:reset
```

Publishes the Firefly reset command and marks the device disconnected until it registers or sends keepalive again.

### 8.4 Get Device Status

```http
GET /api/v1/public/fireflies/{deviceName}/status
```

Response:

```json
{
	"deviceName": "FF01",
	"status": "online",
	"firmwareVersion": "1.2.3",
	"macAddress": "AABBCCDDEEFF",
	"registeredAt": "2026-05-07T10:15:00Z",
	"lastKeepaliveAt": "2026-05-07T10:15:25Z",
	"currentTaskId": "a9d9e5f5-21ce-4afb-a26e-5dd5f4e9db5c"
}
```

### 8.5 Validation and Error Responses

Common public API errors:

- `404 device_not_found`
- `409 device_offline`
- `409 command_in_progress` if queueing is disabled or queue limit is reached.
- `422 invalid_slot_index`
- `422 invalid_action`
- `504 firefly_ack_timeout`
- `502 firefly_error`, including device error code and description.

Public endpoints should never expose raw Python tracebacks or internal actor details.

## 9. Admin API for Frontend

Admin endpoints are intended for the React UI and should be versioned under `/api/v1/admin`.

Recommended endpoints:

```text
GET    /api/v1/admin/mqtt-brokers
POST   /api/v1/admin/mqtt-brokers
PUT    /api/v1/admin/mqtt-brokers/{brokerId}
POST   /api/v1/admin/mqtt-brokers/{brokerId}:test-connection

GET    /api/v1/admin/fireflies
POST   /api/v1/admin/fireflies
GET    /api/v1/admin/fireflies/{deviceId}
PUT    /api/v1/admin/fireflies/{deviceId}
DELETE /api/v1/admin/fireflies/{deviceId}
POST   /api/v1/admin/fireflies/{deviceId}:start-actor
POST   /api/v1/admin/fireflies/{deviceId}:stop-actor
POST   /api/v1/admin/fireflies/{deviceId}:reinitialize
POST   /api/v1/admin/fireflies/{deviceId}:reset

GET    /api/v1/admin/fireflies/{deviceId}/segments
POST   /api/v1/admin/fireflies/{deviceId}/segments
PUT    /api/v1/admin/fireflies/{deviceId}/segments/{segmentId}
DELETE /api/v1/admin/fireflies/{deviceId}/segments/{segmentId}

GET    /api/v1/admin/fireflies/{deviceId}/slots
POST   /api/v1/admin/fireflies/{deviceId}/slots
PUT    /api/v1/admin/fireflies/{deviceId}/slots/{slotId}
DELETE /api/v1/admin/fireflies/{deviceId}/slots/{slotId}
POST   /api/v1/admin/fireflies/{deviceId}/slots:test

GET    /api/v1/admin/led-states
POST   /api/v1/admin/led-states
PUT    /api/v1/admin/led-states/{stateId}
DELETE /api/v1/admin/led-states/{stateId}

GET    /api/v1/admin/command-presets
POST   /api/v1/admin/command-presets
PUT    /api/v1/admin/command-presets/{presetId}
DELETE /api/v1/admin/command-presets/{presetId}

GET    /api/v1/admin/events
GET    /api/v1/admin/events/{eventId}
```

## 10. Frontend Requirements

The React frontend should be an operational management tool, not a marketing site. It should prioritize dense but clear information, predictable navigation, and fast configuration workflows.

The frontend must include the Firefly product logo from `logo-firefly.png`. The logo should be treated as a first-class brand asset and included in the React application's static assets so it is served correctly by the FastAPI backend after the frontend is built. It should appear in the main application shell, such as the top navigation bar or sidebar header, and may also be used on login, loading, or empty-state screens where branding is appropriate. The UI should preserve the logo's aspect ratio, provide accessible alternative text such as `Firefly`, and avoid recoloring or distorting the image.

Main views:

- Dashboard: MQTT broker connection, device count by status, recent errors/timeouts.
- Devices: list of Firefly devices with status, firmware, MAC, last keepalive, enabled flag, and action buttons.
- Device detail: live status, MQTT metadata, actor state, current task ID, reset/reinitialize controls.
- Segment editor: configure channel, segment number, first LED index, last LED index.
- Slot editor: configure slot index, segment, segment position, number of LEDs, optional external identifier, and label.
- LED states: manage reusable low-level Firefly states.
- Command presets: map business-friendly actions to LED state and pattern.
- Manual test panel: select a device and slots, choose action/preset/color, send update, and view ACK/error result.
- Event log: inspect recent registration, init, update, ACK, error, timeout, and keepalive events.

Frontend should use the OpenAPI schema generated by FastAPI either directly or through generated TypeScript client types.

## 11. Startup and Shutdown Behavior

On startup:

1. Load application configuration from the local JSON configuration file.
2. Open the configured local database.
3. Load the active MQTT broker configuration from the `mqtt_brokers` table.
4. If an active MQTT broker exists, connect to it and subscribe to the registration request topic.
5. If no active MQTT broker exists, start the backend and frontend in a not-configured MQTT state so the broker can be created through the UI.
6. Load enabled Firefly devices from the database.
7. Start one actor per enabled device after MQTT is connected.
8. Each actor loads its slots and uses `current_task_id` if available; otherwise it waits for registration or initializes on keepalive according to the protocol behavior.
9. Serve FastAPI routes and the React static frontend.

On shutdown:

1. Stop accepting new API commands.
2. Allow in-flight actor commands to finish within a configurable grace period.
3. Stop MQTT subscriptions.
4. Stop actors.
5. Close database connections.

## 12. Security

Version 1 should include at minimum:

- No API key requirement for version 1 unless a later deployment requirement introduces one.
- The service is expected to run inside a secure Macrolet/customer environment with network-level access control.
- Optional application-level authentication may be added later, but it is not part of the Firefly firmware protocol and should not be confused with device registration or MQTT authentication.
- Secrets loaded from a local JSON configuration file or stored encrypted in the local database, depending on the setting.
- Passwords and MQTT credentials must not be returned by API responses.
- Request/response logging must avoid logging secrets.

Future versions may add user accounts, roles, and OAuth/OIDC integration.

## 13. Configuration

The service should use a local JSON configuration file instead of environment variables. The target deployment is a secure environment, and a file-based configuration is easier to inspect, back up, and support on site.

MQTT broker connection settings should not be duplicated in the application configuration file. They belong in the `mqtt_brokers` database table so they can be managed from the frontend and persisted with the rest of the Firefly configuration. On startup, the backend should load the active broker from `mqtt_brokers`. If no active broker exists, the backend should still start, show the MQTT status as not configured, and allow an administrator or integrator to create the broker configuration through the frontend.

Recommended application configuration file: `config/firefly-appsettings.json`.

Example:

```json
{
	"database": {
		"url": "sqlite:///./data/firefly.db"
	},
	"firefly": {
		"mqttProtocolVersion": "v01.04",
		"ackTimeoutMs": 7000,
		"commandQueueLimitPerDevice": 100
	},
	"events": {
		"retentionDays": 30
	},
	"frontend": {
		"staticFilesPath": "./frontend/dist"
	},
	"logging": {
		"level": "INFO"
	}
}
```

The Firefly MQTT protocol version is an application-level setting because it controls the topic names and registration validation logic. It is not the MQTT broker connection configuration. The reference EndOfLine code uses `v01.04`, but the current production firmware version should be confirmed.

The path to this JSON file should be provided by a command-line argument such as `--config config/firefly-appsettings.json`, or by a documented default search path. Environment variables should not be required for normal operation.

## 14. Testing Requirements

Backend tests:

- Unit tests for MQTT topic builders.
- Unit tests for Pydantic payload serialization aliases.
- Unit tests for high-level action to Firefly state/pattern translation.
- Actor tests for registration, init slots, slot update ACK, slot update error, timeout, and task ID mismatch recovery.
- Repository tests against SQLite.
- FastAPI route tests for public and admin APIs.

Integration tests:

- Use a local MQTT broker container or embedded test broker.
- Simulate Firefly devices publishing register requests, ACKs, errors, and keepalives.
- Verify public API calls produce the expected MQTT messages.
- Verify device status changes after keepalive, registration, ACK, error, and timeout.

Frontend tests:

- Component tests for device list, slot editor, LED state editor, and manual test panel.
- End-to-end smoke test for creating a device, defining segments/slots, and issuing a manual slot update against a mocked backend.

## 15. Open Questions

- Confirm the current Firefly MQTT protocol version string used by production firmware.
- Confirm whether PostgreSQL is actually required, or whether SQLite should be the default because the requested deployment is lightweight and file-based.
- Confirm whether public API slot addressing should use only `slotIndex`, or also support stable external slot identifiers such as `externalSlotId`.
- Confirm whether public commands should wait synchronously for Firefly ACK before returning, or return immediately with an operation ID for polling. Version 1 currently assumes synchronous wait with timeout.
- Confirm expected authentication model for integrators and admin users.
- Confirm whether command queueing per device is acceptable, and what maximum queue length should be enforced.
- Confirm whether dynamic ad hoc colors from public API calls should create temporary LED states, map to existing presets, or be restricted to configured presets only.

## 16. Version 1 Milestones

### Milestone 1: Backend Foundation

- Create FastAPI project structure.
- Configure SQLAlchemy, Alembic, and database models.
- Add settings management.
- Add health endpoint.
- Add basic admin CRUD for devices, segments, slots, LED states, and command presets.

### Milestone 2: MQTT Protocol Layer

- Implement topic builder.
- Implement Pydantic MQTT payload models.
- Implement MQTT client wrapper.
- Add registration request subscription.
- Add tests for topic and payload compatibility.

### Milestone 3: Actor Runtime

- Implement actor registry.
- Implement per-device actor state machine.
- Implement registration, init slots, update slot state, reset, keepalive, ACK, error, and timeout handling.
- Persist device runtime metadata.

### Milestone 4: Public API

- Implement `updateFireflySlots` endpoint.
- Implement update all slots, reset, and status endpoints.
- Add OpenAPI examples.

### Milestone 5: Frontend

- Build React app shell.
- Add `logo-firefly.png` as a frontend static asset and use it in the main application shell.
- Add devices dashboard.
- Add device detail and status view.
- Add segment/slot editors.
- Add LED states and command presets UI.
- Add manual test panel and event log.

### Milestone 6: Integration Testing and Packaging

- Add simulated Firefly device tests.
- Add local MQTT broker test setup.
- Add production configuration documentation.
- Serve built frontend from FastAPI.
- Provide run, migration, and deployment instructions.
