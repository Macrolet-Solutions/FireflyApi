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
- SQLite for the local file-based database.
- A React frontend served by the FastAPI backend.
- An actor-based Firefly runtime using Pykka to manage one actor per Firefly device and serialize MQTT command handling.
- An MQTT client layer for the Firefly protocol.

## 2. Firefly Protocol and Runtime Requirements

The service must implement only the generic Firefly device integration layer. It must not include WCS, sorter, picking, container, order, lane, PDA, or operator-station business logic. Those workflows belong to external client systems that call this service through the public API.

Required Firefly behavior:

- One actor instance manages one configured Firefly device.
- Devices communicate using versioned MQTT topics.
- Device registration is initiated by the Firefly device over MQTT.
- The server accepts or rejects registration based on configured device name and `firefly_interface_version`.
- Registration response includes static LED strip segment definitions and named LED states.
- After registration, the server initializes slots with a generated `task-id`.
- On service startup, each device actor must initialize slots by publishing `init-slots` with a newly generated `task-id`, unless the device has no slots configured (see §5.3).
- Slot updates are serialized per device through `event-id` correlation and ACK/error handling.
- If a command does not receive an ACK within the timeout, the actor retries the command up to `ackMaxRetries` times (default 3) before treating the device as offline for that command path. The initial publish does not count as a retry, so the default policy is 1 initial publish + 3 retries = 4 total publishes per command.
- Device errors such as missing or mismatched task ID cause reinitialization of slots.
- Keepalive messages update device liveness. If no keepalive has been received for `keepaliveDisconnectAfterSeconds` (default 300 s), the device is automatically treated as offline. Only inbound keepalives reset this timer; ACKs, errors, and outbound publishes do not count as liveness signals.
- Slot configuration and segment configuration are persisted in the database.
- Runtime device state is actor-owned: current task ID, pending command, last known slot states, and connection state.

Firefly MQTT topics:

```text
From device:
cmd/ptm/register-req/+
cmd/ptm/register-req/{firefly_interface_version}
ptm/{firefly_interface_version}/{deviceName}/ack
ptm/{firefly_interface_version}/{deviceName}/error
ptm/{firefly_interface_version}/{deviceName}/keepalive

To device:
ff/{firefly_interface_version}/{deviceName}/register-resp
ff/{firefly_interface_version}/{deviceName}/init-slots
ff/{firefly_interface_version}/{deviceName}/update-slot-state
ff/{firefly_interface_version}/{deviceName}/update-all-slots
ff/{firefly_interface_version}/{deviceName}/reset
```

The `reset` topic is **fire-and-forget**. The device performs a hard restart equivalent to pressing the physical reset button. The firmware does **not** publish an ACK or error in response. The service treats the publish as immediately completed; there is no `event-id` correlation, no timeout, and no retry for this command.

Firefly MQTT payload concepts:

- Registration request: firmware version, device ID/name, MAC address.
- Registration response: error flag, error description, event ID, device type, LED segments, named LED states.
- ACK: event ID.
- Error: event ID, error code, error description.
- Keepalive: free memory and battery fields.
- Init slots: event ID, task ID, number of slots, slot definitions.
- Update slot state: event ID, task ID, list of slot state changes.
- Reset: empty payload. No `event-id` is required because no ACK is returned.

## 3. Product Scope

### 3.1 In Scope

- Configure MQTT broker connection settings.
- Configure Firefly devices known to this service.
- Configure each device's LED strip segments.
- Configure logical slots mapped to device LED segments.
- Configure reusable LED states and optional command presets that map friendly names to LED states and firmware-supported slot patterns.
- Detect device registration, online/offline state, keepalive, firmware version, MAC address, last registration time, and last keepalive time.
- Initialize devices after registration or service startup.
- Expose admin APIs used by the React frontend.
- Expose public integration APIs used by external systems.
- Provide a frontend for device management, slot/segment editing, live device status, and manual slot testing.
- Persist configuration. Runtime device state is kept only in the in-memory actor; it is rebuilt on every service start through registration, keepalive, and init-slots flow.
- Maintain per-device actor state for reliable command serialization and ACK/error handling.

### 3.2 Out of Scope

- Full WCS behavior such as container assignment, sort destination calculation, PDA messaging, operator station workflows, and other application-specific operational business rules.
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
- `core.config`: local application settings, database URL, `firefly_interface_version`, timeouts, frontend static path, and logging settings.
- `db.models`: SQLAlchemy ORM models.
- `db.repositories`: database persistence operations.
- `firefly.protocol`: MQTT topics, payload schemas, protocol constants, serializers.
- `firefly.mqtt`: MQTT client wrapper and subscription lifecycle.
- `firefly.actors`: actor registry, device actor, actor messages, retry/timeout handling.
- `firefly.service`: high-level operations used by APIs.
- `frontend`: built React app served as static files by FastAPI.

## 5. Firefly Runtime Model

### 5.1 Actor Registry

The actor registry owns all active Firefly device actors. When an active MQTT broker is configured and connected, it loads all configured devices from the database and starts one actor per device. It also owns the global registration-request subscription:

```text
cmd/ptm/register-req/+
```

When a registration request arrives, the registry parses the device ID/name and forwards the message to the matching device actor. If the device is unknown, the service should log the event and optionally publish a registration error response if enough protocol information is available.

### 5.2 Device Actor State

Each actor should keep these runtime fields:

- `device_id`: internal database ID.
- `device_name`: Firefly MQTT device identifier.
- `status`: unknown, online, offline, register_error.
- `firefly_interface_version`: configured Firefly device interface version used in topic names and registration validation.
- `current_task_id`: in-memory task ID accepted by the device after slot initialization for the current actor/device session.
- `slots`: ordered slot configuration for the device.
- `slot_states`: last known state, pattern, and pattern value for each slot updated through this service.
- `pending_command`: optional command waiting for ACK, including command type, event ID, original payload, deadline, retry count, caller correlation, next state on ACK, and error recovery behavior.
- `last_keepalive_at`, `registered_at`, `mac_address`, `firmware_version`.

### 5.3 Device Actor States

The Python actor should implement this state machine:

- `waiting_ack`: actor has sent one MQTT command that requires ACK and is waiting for ACK, error, or timeout.
- `active`: actor has initialized slots and can accept commands.
- `offline`: actor cannot execute commands until registration or keepalive allows reinitialization.

The actor should not use separate top-level states such as `registering`, `initializing_slots`, or `updating_slots` only to represent ACK waiting. Instead, ACK waiting should be represented by `waiting_ack` plus the structured `pending_command.command_type` field. Supported pending command types are `register_response`, `init_slots`, `update_slot_state`, and `update_all_slots`.

The actor tracks two related but distinct values:

- The **state machine state** (`waiting_ack | active | offline`) describes what the actor is currently doing in its command flow. It controls which incoming messages are valid and which transitions are legal.
- The **status** (`unknown | online | offline | register_error`) is the observable lifecycle value exposed through the public and admin APIs.

Status transitions:

- `unknown`: initial value for a freshly started actor that has not yet had a successful exchange with the device.
- `online`: set when `init-slots` is ACK'd.
- `offline`: set when the keepalive watchdog fires, or when ACK retries are exhausted for any command. State machine state is also `offline`.
- `register_error`: set per the registration rules below. Cleared only by a subsequent valid registration request.

When a keepalive arrives while the state machine is `offline` and `status != register_error`, the actor generates a fresh `task-id`, publishes `init-slots`, and transitions to `waiting_ack` with `pending_command.command_type = init_slots`. Status moves to `online` only when that new `init-slots` is ACK'd.

Both the word `offline` in the state machine and the value `offline` in the status enum refer to the same condition: the actor cannot currently execute commands. The state machine value drives behavior; the status value is what the API exposes.

The pending command should determine what happens after ACK, error, or timeout. For example, ACK for `register_response` should trigger publishing `init-slots`; ACK for `init_slots` should transition the actor to `active`; ACK for `update_slot_state` or `update_all_slots` should update runtime slot state and transition back to `active`.

When a device actor starts, it must load the configured slots. If at least one slot is configured, the actor generates a new `task-id`, publishes `init-slots`, and transitions to `waiting_ack` with `pending_command.command_type = init_slots`. If no slots are configured, the actor does not publish `init-slots`; it remains with state machine `offline` and `status = offline` until slots are added and `:reinitialize` is invoked, or a fresh registration arrives that finds slots configured. The same rule applies after the ACK for a `register_response`: if no slots are configured, the actor skips the `init-slots` step and stays `offline`. The `current_task_id` is actor-owned memory for the current physical device session and must not be persisted as active device state. Historical task IDs may be inspected through `firefly_events` payloads for diagnostics.

Registration requests from the device are preemptive and must be accepted from every actor state, including `register_error`. When a registration request is received, the actor must assume the physical Firefly controller has reset or restarted. It must discard any pending ACK correlation, complete any waiting caller with a retryable device re-registration failure, clear session-specific runtime state such as `current_task_id`, and update registration metadata.

The actor then validates the registration:

- If the request's interface version does not match the configured `firefly_interface_version`, the actor publishes a registration error response with a descriptive `error-descr`, sets `status = register_error`, and remains in `offline`. It does not transition to `waiting_ack`. The device can recover only by sending another registration with a matching version.
- If `firefly_led_states` is empty, the actor cannot produce a valid registration response. It publishes a registration error response with `error-descr` indicating that no LED states are configured, sets `status = register_error`, and remains in `offline`. The device can recover only after the operator configures at least one LED state and the device retries registration.
- Otherwise the actor publishes the registration response with the configured segments and LED states, sets `status` based on subsequent transitions (see §5.3 state machine), and transitions to `waiting_ack` with `pending_command.command_type = register_response`.

`status = register_error` is cleared the next time a valid registration request is processed (i.e. one that does not hit either rejection branch above). Keepalives and command timeouts do not clear `register_error`.

Resetting a device session should be modeled as an action, not a top-level actor state. When the actor needs to reset its session, it should clear `current_task_id`, pending ACK correlation, and session-specific metadata, then either publish the next recovery command and enter `waiting_ack` or mark the device `offline` until registration or keepalive allows reinitialization.

**Hard reset.** An operator-initiated hard reset (admin `:reset`, §9.6) is preemptive from every actor state. The actor must: cancel any pending command and complete its waiting HTTP caller with `503 device_resetting`; clear `current_task_id`, `pending_command`, and `slot_states`; publish the `reset` MQTT message (no `event-id`, no payload); set `status = offline` and state machine to `offline`. The actor stays alive. The watchdog timer is left armed — it may fire during the device's reboot, but firing while already `offline` is a no-op. Recovery happens when the device finishes its physical reboot and sends a fresh registration request, at which point the normal registration flow resumes.

Only one MQTT command that requires ACK is in flight per device actor at any time. Additional API requests are queued through the actor mailbox. The Pykka mailbox is unbounded; Version 1 does not impose a queue depth limit. Misbehaving clients are expected to be controlled at the network/integration layer.

### 5.4 ACK, Error, and Timeout Handling

Every MQTT command requiring confirmation must include a generated UUID `event-id`. The actor starts a timeout when publishing. The timeout should default to 7000 ms and be configurable. When a request body specifies `timeoutMs`, that value applies **per attempt**, not as a total wallclock budget; with the default `ackMaxRetries` of 3 the maximum elapsed time for a fully-retried command is approximately `timeoutMs × 4`.

Commands that time out should be retried up to `ackMaxRetries` times (default 3) before the device is marked offline. The initial publish is not counted as a retry: with the default the actor performs 1 initial publish plus up to 3 retries, for 4 total publishes per command. Each retry must use a new `event-id`, publish the MQTT command again, and start a new ACK timeout. The original HTTP request should remain pending while retries are attempted because public command endpoints use synchronous ACK-waiting semantics.

When an ACK arrives:

- If `event-id` matches the pending command, cancel the timeout and apply the pending command's ACK behavior.
- If the pending command is `register_response`, publish `init-slots` with a new `event-id` and remain in `waiting_ack` for the new `init_slots` pending command.
- If the pending command is `init_slots`, store the accepted `task-id` and transition to `active`.
- If the pending command is `update_slot_state` or `update_all_slots`, update the actor's in-memory slot state and transition to `active`.
- If `event-id` does not match, log a warning and keep waiting.

When an error arrives:

- If `event-id` matches, cancel the timeout and complete the command with a failure.
- If the error code is `NO_TASK_ID_WHEN_UPDATING_CELLS` or `TASK_ID_MISMATCH_UPDATING_CELLS`, reinitialize slots.
- Otherwise mark the device offline according to the pending command type and recovery behavior.

When a timeout expires:

- If retry attempts remain, republish the command with a new `event-id` and continue waiting.
- If the retry limit has been reached, complete the command with a timeout error.
- Mark the device offline after the retry limit is reached.
- Keep the actor alive so it can recover on registration or keepalive.

Device liveness is monitored by a per-actor keepalive watchdog, independent of command timeouts. Only inbound keepalive messages refresh liveness; ACKs, errors, and registrations are processed normally but do not reset the watchdog clock.

Each actor owns a single watchdog timer with `keepaliveDisconnectAfterSeconds` duration (default 300):

- On actor start the watchdog is armed for the first time.
- On every inbound keepalive, the actor cancels the current timer and reschedules a new one for `keepaliveDisconnectAfterSeconds` from now.
- If the timer fires, the callback enqueues a `watchdog_fired` message to the actor's mailbox. When the actor processes that message it transitions its in-memory `status` to `offline` and completes any waiting HTTP caller with a `503 device_offline` error. The actor stays alive and can recover when the next registration or keepalive arrives.

Pykka has no first-class scheduled-message primitive, but the actor can use a `threading.Timer` whose callback issues `self.actor_ref.tell({"type": "watchdog_fired"})` and store the timer reference so the next keepalive can cancel it before rescheduling. The timer runs on a daemon thread; the resulting message is processed serially through the mailbox, so no additional locking is needed in the actor.

## 6. MQTT Protocol

### 6.1 Protocol Version

The service must define a configured Firefly device interface version named `firefly_interface_version`. The confirmed production value at the time of writing is `v01.04`. This is the version segment used in Firefly MQTT topic names and registration validation. It is not the generic MQTT broker protocol version. The value lives in operator configuration so it can be changed without a code release if the firmware interface is bumped. A registration request for a different Firefly interface version must be rejected with a registration error response (see §5.3).

### 6.2 Topic Builder

All MQTT topics must be produced through a single topic builder module to avoid string duplication. Topic names must match the protocol listed in §2 unless a newer firmware protocol is confirmed.

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
			"first-led-inx": 1,
			"last-led-inx": 150
		}
	],
	"states": [
		{
			"name": "NEEDS-ATTENTION",
			"rgb": "0xFF8000",
			"color1-on-ms": 0,
			"color1-fade-up-ms": 0,
			"color1-fade-down-ms": 0,
			"repeat-after-ms": 0,
			"num-rep": 0
		}
	]
}
```

Segment LED indexes in registration responses are 1-based and directional. The fields `first-led-inx` and `last-led-inx` define both the inclusive LED range and the physical growth direction of the segment relative to the controller:

- If `first-led-inx` is lower than `last-led-inx`, the segment grows from the controller toward the end of the LED strip.
- If `first-led-inx` is higher than `last-led-inx`, the segment grows from the end of the LED strip back toward the controller.

Regardless of physical growth direction, configured Firefly slot positions are relative slot-order values within the segment. Slots are adjacent; the service does not derive `pos-in-segm` from a starting LED index.

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
			"to-state": "NEEDS-ATTENTION",
			"pattern": 0,
			"pattern-value": 0
		}
	]
}
```

Example update all slots payload:

```json
{
	"event-id": "67c7f3a1-1c19-4b4e-babd-a31128707e6f",
	"task-id": "a9d9e5f5-21ce-4afb-a26e-5dd5f4e9db5c",
	"to-state": "OFF",
	"pattern": 0,
	"pattern-value": 0
}
```

The `update-all-slots` payload carries a single `to-state`, `pattern`, and `pattern-value` that the firmware applies to every slot configured on the device. There is no per-slot list. `pattern` is an integer using the same enum as `update-slot-state` (see §6.4).

### 6.4 Slot LED Patterns

Slot LED patterns are firmware-defined rendering modes that tell the Firefly device which part of a configured slot should receive the target LED state. They are not LED states themselves.

The service supports this fixed pattern enum:

| Integer | Firmware name | Public API name |
|---|---|---|
| `0` | `LED_PATTERN_FULL` | `full` |
| `1` | `LED_PATTERN_SLOT_ENDS` | `slot_ends` |
| `2` | `LED_PATTERN_SLOT_NO_ENDS` | `slot_no_ends` |
| `3` | `LED_PATTERN_SUBSEGMENTS` | `subsegments` |
| `4` | `LED_PATTERN_MULTICOLOR` | `multicolor` |

`pattern-value` is opaque to this service. Its meaning is firmware-defined and depends on the chosen `pattern`. The service must:

- Accept any non-negative integer for `pattern-value` and forward it to the device unchanged.
- Not validate `pattern-value` against the chosen `pattern`. Whether a value makes sense for a given pattern is the integrator's responsibility.
- Default `pattern-value` to `0` when omitted by callers.

Public API documentation should describe `patternValue` as a count whose interpretation depends on `pattern` and refer integrators to the Firefly firmware reference for exact semantics. The service intentionally does not encode these semantics so that future firmware changes to `pattern-value` behavior do not require a service release.

LED states define the color and timing behavior, such as solid, blink, fade, or pulse. Patterns define where (and how) that state is applied within a slot.

### 6.5 LED States

The system should not seed any default LED states. LED states are deployment-specific and should not be treated as product defaults for this service.

LED states must be configured by an administrator or integrator before a Firefly device can be registered successfully. During device registration, the service returns the currently configured states for that installation. If no states are configured, the service should either reject registration with a clear configuration error or keep the device offline until the configuration is completed.

The frontend should provide a blank initial LED state catalog and allow users to create, edit, duplicate, and delete states. The UI may offer optional examples or templates in documentation, but those examples must not be inserted into the database automatically.

LED states are sent to the Firefly device in the registration response (see §6.3). A state added or modified after a device has registered is **not** automatically pushed to that device; the device picks up the new catalog only on its next registration, which means the device must be reset. Segment configuration behaves the same way for the same reason. After editing LED states or segments, the operator triggers re-registration by clicking the device's **Reset** button in the frontend, which calls the admin `:reset` action (§9.6) and publishes the `reset` MQTT message to the device. The physical reset button on the device hardware is the fallback if MQTT is not available.

### 6.6 MQTT Quality of Service

All Firefly MQTT publications and subscriptions use QoS 0 (at-most-once). The Firefly protocol's application-layer `event-id`, ACK, error, and timeout/retry logic provides delivery confirmation; the service does not depend on MQTT-level QoS, retained messages, or Last Will and Testament.

## 7. Database Model

The database must persist configuration. Runtime device state is not persisted (see §7.2). SQLAlchemy models should use normal integer primary keys and database-level uniqueness constraints.

All `*_at` columns store timestamps as UTC. Application code reading and writing them must use timezone-aware `datetime` values in UTC; never naive local time. The API serializes them to the ISO 8601 millisecond format defined in §8.

Recommended tables:

### 7.1 `mqtt_brokers`

- `id`
- `name`
- `host`
- `port`
- `username`
- `password`: stored as plain text. See §12 for the rationale.
- `use_tls`
- `client_id`
- `created_at`
- `updated_at`

Version 1 permits exactly one row in this table. The admin `POST /api/v1/admin/mqtt-brokers` endpoint rejects creating a second broker with `409 broker_already_configured`. PUT updates the single existing row. DELETE is supported only when no `firefly_devices` reference the broker (see §7.8).

### 7.2 `firefly_devices`

- `id`
- `name`: unique Firefly MQTT device identifier, such as `FF01`.
- `display_name`
- `description`
- `mqtt_broker_id`
- `created_at`
- `updated_at`

This table holds only durable configuration. Runtime device state (status, MAC address, firmware version, last registration/keepalive times, last error) is owned by the in-memory actor and is not persisted, because every actor boot re-runs the registration/init-slots sequence and any persisted snapshot would be stale.

There is no `enabled` flag. Every configured device has an actor started at process boot (assuming MQTT is connected). To remove a device from operation, delete its row; cascading rules in §7.8 remove dependent segments, slots, and events.

### 7.3 `firefly_segments`

- `id`
- `device_id`
- `channel_num`: physical LED channel, normally 1 or 2.
- `segment_num_in_channel`
- `first_led_index`
- `last_led_index`
- `created_at`
- `updated_at`

This maps directly to the Firefly segment configuration returned during registration. `first_led_index` and `last_led_index` are 1-based inclusive LED indexes. Their relative order indicates segment direction, but slot ordering must always increment from the smaller LED index toward the higher LED index.

Validation rules:

- `UNIQUE(device_id, channel_num, segment_num_in_channel)`. Within a device, the `(channel, segment-in-channel)` pair must be unique.
- `first_led_index >= 1` and `last_led_index >= 1`. `first_led_index` may be lower or higher than `last_led_index` (see §6.3 for direction semantics). The two may be equal only when a single-LED segment is legitimate for the deployment.
- Segments on the same `channel_num` of the same device must not overlap in LED range. Two segments overlap when their `[min(first, last), max(first, last)]` ranges intersect.

### 7.4 `firefly_slots`

- `id`
- `device_id`
- `segment_id`
- `slot_index`: internal 1-based index sent to the Firefly device. Server-assigned, not supplied by clients.
- `external_slot_id`: required business/integrator slot identifier used by the public API.
- `label`
- `segment_position`: required 1-based relative slot position within the segment. It is the slot order value sent to Firefly as `pos-in-segm`, not a starting LED index.
- `num_leds`: required, must be `>= 1`.
- `created_at`
- `updated_at`

Validation rules:

- `external_slot_id` must match the regex `^[A-Za-z0-9_-]{1,64}$` and be unique per device.
- `slot_index` is unique per device and assigned **append-only** by the server on create: the server picks the next free 1-based integer in the device. There is no requirement that `slot_index` values within a segment reflect slot order; slot order within a segment is determined by `segment_position`. Clients must not send `slot_index` on POST or PUT.
- A slot belongs to exactly one segment and may not span segments. `segment_id` is immutable on PUT; to move a slot to a different segment, delete it and recreate it.
- `segment_position` is immutable on PUT. To change a slot's position within its segment, delete it and recreate it.
- `segment_position` must be unique within a segment.
- Slots in the same segment are adjacent. The sum of `num_leds` for all slots in the segment must fit inside the segment, i.e. `sum(num_leds) <= segment_led_count`, where `segment_led_count = abs(last_led_index - first_led_index) + 1`.
- Mutable PUT fields: `external_slot_id`, `label`, `num_leds`. Changes to `num_leds` must re-check the segment capacity rule above.

The configured `slot_index` is sent to Firefly as `slot-inx`. Public integration APIs must not expose `slot_index`; they must accept `externalSlotId` and resolve it to `slot_index` internally.

### 7.5 `firefly_led_states`

- `id`
- `name`: unique state name.
- `rgb`: string in `0xRRGGBB` format.
- `color1_on_ms`
- `color1_fade_up_ms`
- `color1_fade_down_ms`
- `repeat_after_ms`
- `num_repetitions`
- `created_at`
- `updated_at`

### 7.6 `firefly_command_presets`

- `id`
- `name`: deployment-defined friendly name.
- `led_state_id`
- `pattern`
- `pattern_value`
- `created_at`
- `updated_at`

This table maps deployment-defined preset names to low-level device state and pattern values.

### 7.7 `firefly_events`

Each row records a single MQTT message or actor lifecycle moment (publish, receipt, timeout, retry). Rows are insert-only; there are no in-place status transitions. A logical command therefore spans multiple rows correlated by `event_id`.

- `id`
- `device_id`
- `event_id`: correlation UUID. Outbound commands (`register_response_sent`, `init_slots_sent`, `update_slot_state_sent`, `update_all_slots_sent`, `retry`) generate or reuse this UUID. The matching `ack_received`, `error_received`, and `timeout` rows carry the same `event_id` so a command and its outcome can be joined.
- `event_type`: one of `register_request_received`, `register_response_sent`, `init_slots_sent`, `update_slot_state_sent`, `update_all_slots_sent`, `reset_sent`, `ack_received`, `error_received`, `keepalive_received`, `timeout`, `retry`. The `reset_sent` rows carry a generated UUID in `event_id` for log identification only; no ACK correlation row will follow.
- `task_id`: nullable. Present on `init_slots_sent`, `update_slot_state_sent`, `update_all_slots_sent`.
- `payload_json`: nullable. Full JSON body of the MQTT message for inbound and outbound rows.
- `error_code`: nullable. Set on `error_received` rows.
- `error_description`: nullable. Set on `error_received` rows.
- `created_at`

Indexes:

- `(device_id, created_at DESC)` for log queries.
- `(event_id)` for command-outcome correlation.

Retention is enforced by a daily background task (single-process scheduled job, for example APScheduler) that runs at a fixed UTC time (suggested 03:00 UTC) and deletes rows where `created_at < now - events.retentionDays` (see §13). The job runs in the same process as FastAPI; no external cron is required.

### 7.8 Foreign Key Behavior

| Parent | Child | On parent delete |
|---|---|---|
| `mqtt_brokers` | `firefly_devices` | `RESTRICT` |
| `firefly_devices` | `firefly_segments` | `CASCADE` |
| `firefly_devices` | `firefly_slots` | `CASCADE` |
| `firefly_devices` | `firefly_events` | `CASCADE` |
| `firefly_segments` | `firefly_slots` | `RESTRICT` |
| `firefly_led_states` | `firefly_command_presets` | `RESTRICT` |

`RESTRICT` deletes return `409 in_use` from the admin API with a message indicating which dependent rows block the deletion (e.g. "broker has 3 assigned devices"). Cascading deletes are silent at the database layer and produce a successful 204 response.

## 8. Public Integration API

Public endpoints are intended for external applications that want to control Firefly devices without knowing MQTT details. They should be stable, documented through OpenAPI, and versioned under `/api/v1/public`.

Public command endpoints must use synchronous ACK-waiting semantics for version 1. The HTTP request should remain open until the Firefly device ACKs the MQTT command, returns a Firefly error, or the configured ACK timeout expires. A successful ACK should return a success response, a Firefly error should return a `502 firefly_error`, and an ACK timeout should return `504 firefly_ack_timeout`.

All timestamps exchanged through the public and admin APIs use **RFC 3339 / ISO 8601 in UTC with a trailing `Z` and millisecond precision**, for example `2026-05-07T10:15:00.123Z`. Inputs must be UTC; the service rejects local-time or offset-suffixed timestamps in request bodies. Outputs are always UTC. This convention is shared by every endpoint in §8 and §9.

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
			"externalSlotId": "SLOT-001",
			"stateName": "READY",
			"pattern": "full",
			"patternValue": 0
		},
		{
			"externalSlotId": "SLOT-002",
			"stateName": "NEEDS-ATTENTION",
			"pattern": "slot_ends",
			"patternValue": 10
		},
		{
			"externalSlotId": "SLOT-003",
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
	"currentTaskId": "a9d9e5f5-21ce-4afb-a26e-5dd5f4e9db5c",
	"clientRequestId": "optional-client-correlation-id"
}
```

The `currentTaskId` field is runtime actor state exposed for diagnostics. It comes from the active in-memory device actor, not from a persisted device table column.

`timeoutMs` is per-attempt (see §5.4); with the default `ackMaxRetries` of 3 a fully-retried command may keep the HTTP request open for approximately `timeoutMs × 4`.

The preferred version 1 contract is explicit for integrators while hiding Firefly hardware indexes: callers provide an `externalSlotId`, a configured `stateName`, and optional `pattern` and `patternValue` information. The service resolves `externalSlotId` to the configured internal `slot_index`, validates that the state exists in `firefly_led_states`, validates that the pattern is one of the fixed firmware-supported pattern values, translates the request into Firefly `slot-inx`, `to-state`, `pattern`, and `pattern-value` fields, and sends one MQTT `update-slot-state` command to the device actor.

The public API must not accept Firefly `slotIndex` directly. `slot_index` is an internal hardware mapping managed through admin configuration so that external systems can use stable business identifiers without depending on physical slot numbering.

If `pattern` is omitted, the service should default it to `full`. If `patternValue` is omitted, the service should default it to `0`. For patterns where firmware gives `pattern-value` a special meaning, callers may provide a non-zero `patternValue`.

The `stateName` must already exist in `firefly_led_states`. LED states are sent to the device only during registration, so a state added after the device registered is not yet known to the firmware and using it will result in a Firefly error from the device; see §6.5. For example, turning a slot off is not a built-in command unless the installation has configured an LED state such as `OFF` with RGB `0x000000` and the device has been registered with that state in its catalog.

Supported pattern values for the public API (full mapping in §6.4):

- `full`: maps to Firefly pattern `0`. `patternValue` is ignored by firmware; the service still forwards whatever is sent.
- `slot_ends`: maps to Firefly pattern `1`.
- `slot_no_ends`: maps to Firefly pattern `2`.
- `subsegments`: maps to Firefly pattern `3`.
- `multicolor`: maps to Firefly pattern `4`.

`patternValue` is forwarded to the device as an opaque non-negative integer. Its meaning depends on the chosen `pattern` and is firmware-defined; the service does not validate or interpret it.

Optional higher-level presets may be added as a convenience layer, but they should resolve to the same explicit fields before reaching the actor. For example, a preset named `warning` may resolve to `stateName: "NEEDS-ATTENTION"`, `pattern: "slot_ends"`, and a specific `patternValue`. Presets should not replace direct state-based control in the core public API.

### 8.2 Update All Slots

```http
POST /api/v1/public/fireflies/{deviceName}/slots:update-all
```

Request:

```json
{
	"stateName": "OFF",
	"pattern": "full",
	"patternValue": 0,
	"clientRequestId": "optional-client-correlation-id",
	"timeoutMs": 7000
}
```

This endpoint applies the same configured state and pattern to every slot the firmware currently has in its slot table; the service does not filter the list. As with `updateFireflySlots`, `stateName` must already exist in `firefly_led_states`; see §6.5 for how new LED states reach the device.

### 8.3 Get Device Status

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
	"registeredAt": "2026-05-07T10:15:00.000Z",
	"lastKeepaliveAt": "2026-05-07T10:15:25.142Z",
	"currentTaskId": "a9d9e5f5-21ce-4afb-a26e-5dd5f4e9db5c"
}
```

All fields except `deviceName` and `status` are nullable and reflect what the actor has observed in the current service session. When the actor has just started and has not yet received a registration, keepalive, or ACK from the device, `status` is `"unknown"` and every other field is `null`. None of these values are read from the database.

### 8.4 Validation and Error Responses

All public and admin error responses use this JSON shape:

```json
{
	"errorCode": "device_not_found",
	"errorDescription": "no device named FF99",
	"details": {}
}
```

`errorCode` is a stable machine-readable token from the list below. `errorDescription` is a human-readable message and may vary across builds. `details` is an optional object for additional context (for example, the Firefly device's `error-code` and `error-descr` on `502 firefly_error`).

Common public API errors:

- `404 device_not_found`
- `409 device_offline`
- `422 invalid_external_slot_id`
- `422 invalid_state_name`
- `422 invalid_pattern`
- `502 firefly_error`, with device error code and description in `details`.
- `503 broker_unavailable` when there is no usable MQTT broker connection. Covers all of: no broker row configured, broker connection currently down, or broker still reconnecting. Distinct from `409 device_offline`, which means the specific device is silent while the broker is reachable.
- `504 firefly_ack_timeout`

Public endpoints should never expose raw Python tracebacks or internal actor details.

## 9. Admin API for Frontend

Admin endpoints are intended for the React UI and should be versioned under `/api/v1/admin`.

Recommended endpoints:

```text
GET    /api/v1/admin/mqtt-brokers
GET    /api/v1/admin/mqtt-brokers/{brokerId}
POST   /api/v1/admin/mqtt-brokers
PUT    /api/v1/admin/mqtt-brokers/{brokerId}
DELETE /api/v1/admin/mqtt-brokers/{brokerId}
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

Standard CRUD endpoints follow conventional REST semantics with JSON bodies that mirror the database models from §7, omitting secrets. The subsections below define the non-CRUD action endpoints, which all use the verb-colon form.

### 9.1 Test MQTT Broker Connection

```http
POST /api/v1/admin/mqtt-brokers/{brokerId}:test-connection
```

Request body: empty.

Opens a transient MQTT connection using the stored broker configuration, waits for CONNACK with a bounded timeout (5000 ms), and disconnects immediately. Does not affect the active broker connection or running actors.

Response on success:

```json
{
	"brokerId": 1,
	"success": true,
	"connectedAt": "2026-05-11T10:15:00.000Z"
}
```

Response on failure: HTTP 502 with body:

```json
{
	"brokerId": 1,
	"success": false,
	"errorCode": "broker_unreachable",
	"errorDescription": "connect timeout after 5000 ms"
}
```

Possible `errorCode` values: `broker_unreachable`, `broker_auth_failed`, `broker_tls_failed`, `broker_protocol_error`.

### 9.2 Start Device Actor

```http
POST /api/v1/admin/fireflies/{deviceId}:start-actor
```

Request body: empty.

Starts the actor for the device if it is not already running. The actor runs the boot sequence in §5.3 (load slots, generate `task-id`, publish `init-slots`, enter `waiting_ack`). If the device has no slots configured, the actor still starts but skips the `init-slots` publish (see §5.3). Idempotent.

Returns 409 `broker_not_connected` if there is no active MQTT broker connection.

Response:

```json
{
	"deviceId": 1,
	"actorStatus": "started"
}
```

`actorStatus` is one of `started` or `already_running`. This endpoint does not wait for `init-slots` ACK; the boot sequence runs asynchronously in the actor. Use `:reinitialize` to wait for ACK.

### 9.3 Stop Device Actor

```http
POST /api/v1/admin/fireflies/{deviceId}:stop-actor
```

Request body: empty.

Stops the actor cleanly: cancels any pending command and its watchdog timer, completes any waiting HTTP caller with a `503 actor_stopped` error, and removes the actor from the registry. The device row in `firefly_devices` is left untouched; a subsequent `:start-actor` (or a backend restart) re-creates the actor. Idempotent.

Response:

```json
{
	"deviceId": 1,
	"actorStatus": "stopped"
}
```

`actorStatus` is one of `stopped` or `already_stopped`.

### 9.4 Reinitialize Device

```http
POST /api/v1/admin/fireflies/{deviceId}:reinitialize
```

Request:

```json
{
	"timeoutMs": 7000
}
```

`timeoutMs` is optional and overrides `ackTimeoutMs` for this single command (per-attempt; see §5.4). Use after changing slot configuration so the device picks up the new slot layout. Segment configuration and the LED state catalog are sent only in the registration response; to apply changes to those, the device must re-register, which is done by triggering `:reset` (§9.6) — `:reinitialize` will not push them.

Instructs the actor to generate a new `task-id` and publish `init-slots`. Uses synchronous ACK-waiting semantics: the HTTP request remains open until ACK, error, or timeout.

Response:

```json
{
	"deviceId": 1,
	"status": "reinitialized",
	"eventId": "67c7f3a1-1c19-4b4e-babd-a31128707e6f",
	"currentTaskId": "a9d9e5f5-21ce-4afb-a26e-5dd5f4e9db5c"
}
```

Error mapping matches the public command endpoints: 502 `firefly_error`, 504 `firefly_ack_timeout`, 409 `device_offline`, 409 `actor_not_running`.

### 9.5 Test Slot Update

```http
POST /api/v1/admin/fireflies/{deviceId}/slots:test
```

Used by the manual test panel in the UI. Behaves like the public `updateFireflySlots` endpoint (§8.1) but accepts internal `slotId` values rather than `externalSlotId` because the admin UI works with database identifiers.

Request:

```json
{
	"slots": [
		{
			"slotId": 7,
			"stateName": "NEEDS-ATTENTION",
			"pattern": "slot_ends",
			"patternValue": 10
		}
	],
	"timeoutMs": 7000
}
```

Defaults and validation rules for `pattern`, `patternValue`, and `stateName` are identical to §8.1.

Response: identical shape to §8.1 minus `clientRequestId`, which is not part of the admin request and is not echoed back.

### 9.6 Reset Device

```http
POST /api/v1/admin/fireflies/{deviceId}:reset
```

Request body: empty.

Publishes the `reset` MQTT message (§2) to the device, which triggers a hard restart equivalent to pressing the physical reset button. This is the supported way to make a device pick up changes to LED state catalog or segment configuration, since those values are sent only in the registration response (see §6.5).

This action is fire-and-forget at the MQTT layer — the device does not ACK and no timeout/retry is applied. The endpoint returns as soon as the MQTT publish has been handed to the client library. The actor performs the steps described under "Hard reset" in §5.3 before returning: cancels any pending command (the waiting HTTP caller receives `503 device_resetting`), clears `current_task_id` / `pending_command` / `slot_states`, sets `status = offline`, and waits for the device's next registration.

Response:

```json
{
	"deviceId": 1,
	"status": "reset_published",
	"eventId": "67c7f3a1-1c19-4b4e-babd-a31128707e6f"
}
```

`eventId` is the UUID written to `firefly_events.event_id` on the `reset_sent` row (§7.7) for traceability; it is not used for any ACK correlation.

Errors:

- `409 actor_not_running` if no actor exists for the device.
- `503 broker_unavailable` if there is no usable MQTT broker connection.

Because the device is about to reboot, callers should expect `GET /status` to report `offline` continuously until the device finishes booting, re-registers, and the subsequent `init-slots` is ACK'd, at which point status transitions to `online` (see the status rules in §5.3).


## 10. Frontend Requirements

The React frontend should be an operational management tool, not a marketing site. It should prioritize dense but clear information, predictable navigation, and fast configuration workflows.

The frontend must include the Firefly product logo from `logo-firefly.png`. The source file ships alongside this specification document (same directory). During the build it must be copied into the React application's static assets directory (for example `frontend/src/assets/logo-firefly.png`) so it is bundled by Vite/CRA and served correctly by the FastAPI backend after the frontend is built. It should appear in the main application shell, such as the top navigation bar or sidebar header, and may also be used on login, loading, or empty-state screens where branding is appropriate. The UI should preserve the logo's aspect ratio, provide accessible alternative text such as `Firefly`, and avoid recoloring or distorting the image.

Main views:

- Dashboard: MQTT broker connection, device count by status, recent errors/timeouts.
- Devices: list of Firefly devices with status, firmware, MAC, last keepalive, and action buttons.
- Device detail: live status, MQTT metadata, actor state, current task ID, **Reset** control (calls `:reset`, §9.6), reinitialize control.
- Segment editor: configure channel, segment number, first LED index, last LED index. Saving changes shows a banner reminding the operator that the device must be reset (via the **Reset** button on the device detail page) for segment changes to take effect.
- Slot editor: configure the required external slot identifier, segment, segment position, number of LEDs, and label. `slot_index` is server-assigned and is shown read-only.
- LED states: manage reusable low-level Firefly states. Saving changes shows the same reset-required banner as the segment editor.
- Command presets: map friendly preset names to LED state and pattern.
- Manual test panel: select a device and slots, choose a configured state, pattern, optional pattern value, or preset, send update, and view ACK/error result.
- Event log: inspect recent registration, init, update, ACK, error, timeout, and keepalive events.

Frontend should use the OpenAPI schema generated by FastAPI either directly or through generated TypeScript client types.

## 11. Startup and Shutdown Behavior

On startup:

1. Load application configuration from the local JSON configuration file.
2. Open the configured local database. If the SQLite file does not yet exist at the configured path, create it (along with its parent directory).
3. Run `alembic upgrade head` against the database. If migrations fail, abort startup with a clear log message; do not proceed to MQTT or actor initialization with a partial schema.
4. Load the active MQTT broker configuration from the `mqtt_brokers` table.
5. If an active MQTT broker exists, connect to it and subscribe to the registration request topic.
6. If no active MQTT broker exists, start the backend and frontend in a not-configured MQTT state so the broker can be created through the UI.
7. Load configured Firefly devices from the database.
8. Start one actor per device after MQTT is connected.
9. Each actor loads its slots, generates a new `task-id`, publishes `init-slots`, and waits for ACK (or skips the publish if no slots are configured; see §5.3). The actor must do this on every startup because `current_task_id` is not persisted as active state across service processes.
10. Serve FastAPI routes and the React static frontend.

Broker configuration is treated as fixed at process start. Creating or changing the broker row in `mqtt_brokers` does not take effect in a running backend; an administrator must restart the backend for the new broker configuration to be loaded and for actors to start. This is deliberate — it keeps the broker connection state simple in Version 1.

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
- MQTT broker credentials are stored as **plain text** in the `mqtt_brokers` table. The deployment relies on operating-system filesystem permissions on the SQLite database file and on network-level access control around the host; no application-level encryption is applied. This is a deliberate Version 1 choice.
- Passwords and MQTT credentials must never be returned in API responses. Admin GETs for `mqtt_brokers` must redact the password field.
- Request/response logging must avoid logging secrets.

Future versions may add user accounts, roles, and OAuth/OIDC integration.

## 13. Configuration

The service should use a local JSON configuration file instead of environment variables. The target deployment is a secure environment, and a file-based configuration is easier to inspect, back up, and support on site.

MQTT broker connection settings live in the `mqtt_brokers` database table (see §7.1), not in this configuration file, so they can be managed from the frontend. The single configured broker is loaded once at process start. If no broker row exists, the backend still starts in a not-configured state so the broker can be created through the UI, but a backend restart is required after the broker is created before actors will run (see §11).

Recommended application configuration file: `config/firefly-appsettings.json`.

Example:

```json
{
	"database": {
		"url": "sqlite:///./data/firefly.db"
	},
	"firefly": {
		"firefly_interface_version": "v01.04",
		"ackTimeoutMs": 7000,
		"ackMaxRetries": 3,
		"keepaliveDisconnectAfterSeconds": 300
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

The `firefly_interface_version` is an application-level setting because it controls the topic names and registration validation logic. It is not the MQTT broker connection configuration and is not the generic MQTT protocol version. See §6.1 for the confirmed production value.

`ackMaxRetries` counts retries only and does not include the initial publish. With the default value of 3, the actor performs 1 initial publish plus up to 3 retries (4 total publishes) before completing the command with a timeout error and marking the device offline.

The path to this JSON file is resolved in this order of precedence:

1. The `--config <path>` command-line argument, if supplied.
2. The default path `./config/firefly-appsettings.json` relative to the process working directory.

If neither produces a readable file, startup aborts with a clear error. Environment variables are not used for normal operation.

## 14. Testing Requirements

Backend tests:

- Unit tests for MQTT topic builders.
- Unit tests for Pydantic payload serialization aliases.
- Unit tests for segment direction and 1-based LED index handling when deriving Firefly slot order.
- Unit tests for state, pattern, pattern value, and preset translation to Firefly MQTT payloads.
- Actor tests for registration, startup init slots, slot update ACK, slot update error, timeout, registration preemption while waiting for ACK, and task ID mismatch recovery.
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

None at this time. Earlier open questions about `firefly_interface_version` and `patternValue` semantics have been resolved in §6.1 and §6.4 respectively. Version 1 deliberately leaves the actor mailbox unbounded; future versions may revisit if integration patterns require backpressure.

## 16. Version 1 Milestones

These milestones are structured for incremental code generation: each phase produces a runnable, testable artifact, and each phase boundary is a natural review point. Phases are intended to be executed sequentially with no backtracking.

### Phase 1: Foundation and Admin CRUD

Goal: a runnable backend that can be configured through HTTP, with persistence working end-to-end and no MQTT involvement yet.

- Create FastAPI project structure and `core.config` JSON loader (§13), with the documented `--config` / default search-path resolution.
- Configure SQLAlchemy, Alembic, and the initial schema migration covering every table in §7.
- Define Pydantic request/response schemas mirroring §7 (omitting secrets per §12).
- Implement repositories (`db.repositories`) for all tables, including the single-row constraint on `mqtt_brokers` (§7.1) and the foreign-key behavior in §7.8.
- Implement admin CRUD endpoints for brokers, devices, segments, slots, LED states, and command presets (§9 CRUD entries), including the validation rules in §7.3 / §7.4 and the standardized error envelope (§8.4).
- Repository unit tests against an in-memory SQLite, route tests with FastAPI's TestClient.

End state: backend starts with `--config <path>`, applies migrations, serves admin CRUD, returns redacted broker rows.

### Phase 2: MQTT Protocol and Actor Runtime

Goal: the runtime works end-to-end against a simulated Firefly device. No HTTP command surface yet — drive it from tests.

- Implement the topic builder (§6.2) and Pydantic payload models with JSON-name aliases (§6.3), including the directional segment semantics (§6.3, §7.3) and the pattern enum (§6.4).
- Implement the MQTT client wrapper (`firefly.mqtt`) with QoS 0 publish/subscribe (§6.6), no LWT, no retained messages, and the global `cmd/ptm/register-req/+` subscription (§5.1).
- Implement the actor registry and per-device actor (`firefly.actors`) using Pykka, with the state machine and status enum from §5.3.
- Implement the boot sequence, including the no-slots-configured branch (§5.3, §9.2 note).
- Implement ACK / error / timeout / retry handling per §5.4, including per-attempt `timeoutMs` semantics.
- Implement the keepalive watchdog using `threading.Timer` and the `watchdog_fired` mailbox message (§5.4).
- Implement registration preemption (§5.3) and the "Hard reset" action (§5.3, no ACK, no correlation).
- Write every MQTT publish and every received message to `firefly_events` per the multi-row schema in §7.7. Implement the daily retention background job (§7.7).
- Actor unit tests covering: registration, startup `init-slots`, slot-update ACK / error / timeout / retry, registration preemption while waiting for ACK, `NO_TASK_ID_WHEN_UPDATING_CELLS` / `TASK_ID_MISMATCH_UPDATING_CELLS` recovery, watchdog firing, keepalive-in-offline triggering fresh `init-slots`, hard reset clearing session state.

End state: a test can simulate a Firefly device over MQTT and observe the actor running the full lifecycle correctly. No public/admin HTTP surface for commands yet.

### Phase 3: Public and Admin HTTP Surface

Goal: full backend feature-complete, exercised against a real MQTT broker.

- Implement the service layer (`firefly.service`) that translates HTTP requests into actor messages with synchronous ACK-waiting semantics (§8).
- Public endpoints: `updateFireflySlots` (§8.1), `update-all-slots` (§8.2), status (§8.3).
- Admin action endpoints: `:test-connection` (§9.1), `:start-actor` (§9.2), `:stop-actor` (§9.3), `:reinitialize` (§9.4), `slots:test` (§9.5), `:reset` (§9.6).
- Apply the standardized error envelope (§8.4) consistently across both public and admin error paths.
- Add the startup sequence from §11 (load config → migrations → load single broker → connect → start actors per configured device → serve routes), including the broker-not-configured path and the documented restart requirement.
- Add OpenAPI examples for every endpoint.
- Integration tests against a containerized MQTT broker (for example `eclipse-mosquitto`) with a simulated device, covering: status transitions through registration / keepalive / ACK / error / timeout, public API → MQTT message correctness, `:reset` flow.

End state: backend is feature-complete and can be exercised by curl / HTTP clients.

### Phase 4: Frontend

Goal: full React UI bound to the generated OpenAPI client.

- React app shell with routing.
- Generate the TypeScript API client from FastAPI's OpenAPI schema.
- Copy `logo-firefly.png` into the React assets (§10) and place it in the application shell.
- Dashboard: broker status, device counts by status, recent errors/timeouts.
- Devices list with status, firmware, MAC, last keepalive, action buttons.
- Device detail view with live status, actor state, current task ID, **Reset** button (`:reset`, §9.6), reinitialize control.
- Segment editor and slot editor with the reset-required banner after save (§10).
- LED states editor with the reset-required banner.
- Command presets editor.
- Manual test panel using the admin `slots:test` endpoint.
- Event log view backed by `firefly_events`.
- Component tests for the editors and manual test panel; end-to-end smoke test against a mocked backend (create device → define segments/slots → issue manual update).

End state: usable web UI for configuration, status monitoring, and manual testing.

### Phase 5: Packaging and Documentation

Goal: deployable build with operator-facing instructions.

- Serve the built React app as static files from FastAPI (§4 module layout, `frontend.staticFilesPath` config).
- Production configuration example (`config/firefly-appsettings.json`).
- Run, migration, and deployment instructions (README).
- Document the operator workflows that depend on backend restart (broker creation/change, §11) and on device reset (LED state / segment changes, §6.5).

End state: a runnable artifact with documentation; ready for a first deployment.
