# Firefly Public API Integration Guide

## Document And API Version

| Item | Value |
|---|---|
| Document version | 0.1 |
| Document date | 2026-06-30 |
| API namespace | `/api/v1/public` |
| API status | Initial customer integration guide |
| Product | Macrolet Firefly API Service |

This document describes the public HTTP API exposed by the Firefly API Service for external customer systems. It is intended for WMS, WES, WCS, picking-cart, sorter, and other integration developers that need to control Firefly slot states without using the low-level Firefly MQTT protocol directly.

The public API is separate from the admin API used by the bundled web frontend. Customers should use the frontend to configure devices, MQTT broker settings, LED states, segments, and static slot layouts. External systems should use only the public API endpoints documented here.

## Overview

The Firefly API Service is a local middleware service for Macrolet Firefly hardware. A Firefly controller drives LED strips and receives commands through MQTT. The Firefly API Service hides the device MQTT protocol behind a local HTTP API and a browser-based configuration frontend.

Typical responsibilities are split as follows:

| Responsibility | Owner |
|---|---|
| MQTT connection, device registration, ACK/error handling, task IDs | Firefly API Service |
| Device, segment, LED state, and static slot configuration | Firefly frontend |
| Operational decisions such as which box or slot should light | Customer system |
| Public slot update calls | Customer system |

The service is normally deployed locally on the customer site, often on a Windows machine as a Windows service. The HTTP API is therefore usually reached through a local network URL such as:

```text
http://<firefly-api-host>:8000/api/v1/public
```

The default port is `8000`, but it can be changed in the service configuration file.

## Local Deployment Model

The Firefly API Service can be bundled and installed as a Windows service. In that deployment mode:

| Item | Default |
|---|---|
| Windows service name | `MacroletFireflyApi` |
| Display name | `Macrolet Firefly API` |
| Default HTTP port | `8000` |
| Default database | Local SQLite database |
| Default logs folder | `AppLogs` |
| Bundled frontend | Served by the same HTTP service |

After installation, customer users normally open the frontend in a browser:

```text
http://<firefly-api-host>:8000/
```

Developers can inspect the generated OpenAPI page when enabled:

```text
http://<firefly-api-host>:8000/docs
```

The public integration API described in this document uses:

```text
http://<firefly-api-host>:8000/api/v1/public
```

Network access, firewall rules, and any customer-side reverse proxy or VPN access should be handled by the deployment environment. The current API does not document an application-level authentication scheme.

## Core Concepts

### Device Name

A Firefly device is addressed by `deviceName` in the public API URL:

```text
/api/v1/public/fireflies/{deviceName}/...
```

`deviceName` must match the configured Firefly device name in the frontend. This is also the device identifier used by the Firefly MQTT protocol.

### Segments

A segment is a physical LED strip connected to a Firefly controller. For example, in multi-level layouts such as picking carts, each level has a physical LED strip, connected to the next via cable. Segments are configured in the frontend and are identified by:

<figure class="concept-figure">
  <img src="pdf/assets/drawing-segments.png" alt="Firefly segment layout showing LED strips connected by channel and segment numbering." />
  <figcaption>Example segment layout: each physical LED strip is configured as a segment and addressed by channel number and segment number within the channel.</figcaption>
</figure>

| Field | Meaning |
|---|---|
| `channelNum` | Controller channel number, starting at `1` |
| `segmentNumInChannel` | Segment number within that channel, starting at `1` |

Segments can be configured in one of two modes:

| Mode | Meaning |
|---|---|
| `static` | Slot layout is fixed and configured in the frontend. |
| `dynamic` | Slot layout is loaded by the public `load-slots` endpoint. Slots cannot be manually configured for this segment in the frontend. |

A segment can only be switched from `static` to `dynamic` after all existing slots have been removed from that segment.

### Slots

A slot is a logical addressable area within a segment. For example, a slot can represent a tote, box, bin, carton, or picking position.

Public API callers identify slots by `externalSlotId`. The customer system should treat this as the stable slot identifier.

Internally, the Firefly API Service maps each `externalSlotId` to a numeric `slot-inx` used by the Firefly firmware. Public callers should not store or depend on `slot-inx`. The internal `slot-inx` can change whenever a dynamic layout is loaded.

### External Slot ID

`externalSlotId` is the public identifier used by customer systems.

Constraints:

| Constraint | Value |
|---|---|
| Required | Yes |
| Type | String |
| Length | 1 to 64 characters |
| Allowed characters | `A-Z`, `a-z`, `0-9`, `_`, `-` |
| Pattern | `^[A-Za-z0-9_-]{1,64}$` |

The same `externalSlotId` cannot be used twice on the same Firefly device at the same time.

### LED States

LED states are configured in the frontend. Public API callers reference them by name using `stateName`.

Examples:

```text
PICK
PUT
ERROR
OFF
NEEDS-ATTENTION
```

The actual names depend on the site configuration. If a public API request references an unknown state, the service returns `422 invalid_state_name`.

### Patterns

Slot update endpoints support a `pattern` field. If omitted, the service uses `full`.

| Public value | Firmware value | Meaning |
|---|---:|---|
| `full` | `0` | Light the full slot. |
| `slot_ends` | `1` | Light slot ends. |
| `slot_no_ends` | `2` | Light the slot excluding ends. |
| `subsegments` | `3` | Firmware subsegment pattern. |
| `multicolor` | `4` | Firmware multicolor pattern. |

`patternValue` is an integer modifier for the selected firmware pattern. Use `0` unless Macrolet provides a pattern-specific value for the integration.

## Typical Workflows

### Static Slot Layout

Use this workflow when the physical slot layout is fixed.

1. Configure MQTT broker, Firefly device, LED states, segments, and slots in the frontend.
2. Reinitialize or reset the device as needed from the frontend so the controller receives the configured slot layout.
3. Customer system calls `slots:update` whenever it needs to change one or more slot states.

The customer system does not call `load-slots` for static segments.

### Dynamic Slot Layout

Use this workflow when the slot layout changes during operation, such as a picking cart where box widths vary by picking tour.

1. Configure the Firefly device, LED states, and physical segments in the frontend.
2. Mark the relevant segments as `dynamic` in the frontend.
3. At the start of a tour or layout change, call `load-slots` once for the Firefly device.
4. Wait for `load-slots` to return success. The service has sent the new slot layout to the controller and received an ACK.
5. Call `slots:update` using the stable `externalSlotId` values from the loaded layout.

The `load-slots` endpoint can load several dynamic segments for the same device in one request. This allows one API call per Firefly device per tour or layout change.

### Clearing A Dynamic Segment

To remove all slots from a dynamic segment, include the segment with an empty `slots` array:

```json
{
  "segments": [
    {
      "channelNum": 2,
      "segmentNumInChannel": 1,
      "slots": []
    }
  ]
}
```

After this succeeds, `slots:update` calls for external slot IDs that were removed from that segment will fail with `invalid_external_slot_id`.

## Common Response: CommandResponse

Most public command endpoints return the same response shape.

```json
{
  "deviceName": "FF01",
  "status": "updated",
  "eventId": "5c563765-8d30-49df-a8cc-dc35066b4f49",
  "currentTaskId": "29348e15-e468-4919-ad5c-97576d48ca82",
  "clientRequestId": "client-123"
}
```

| Field | Type | Meaning |
|---|---|---|
| `deviceName` | string | Firefly device name from the URL. |
| `status` | string | Operation result. Common values are `updated` and `loaded`. |
| `eventId` | string | Service-generated command correlation ID used for MQTT ACK/error handling. |
| `currentTaskId` | string or null | Current Firefly task ID accepted by the device after slot initialization. |
| `clientRequestId` | string or null | Caller-provided correlation ID when the endpoint supports it. |

`eventId` and `currentTaskId` are useful for support and diagnostics. Public API callers should not use them as business identifiers.

## Error Responses

All API errors use a standard JSON envelope.

```json
{
  "errorCode": "invalid_external_slot_id",
  "errorDescription": "External slot id 'BOX-999' is not configured for this device.",
  "details": {}
}
```

| Field | Type | Meaning |
|---|---|---|
| `errorCode` | string | Machine-readable error code. |
| `errorDescription` | string | Human-readable error message. |
| `details` | object | Optional structured details. |

Common HTTP statuses:

| Status | Meaning |
|---:|---|
| `400` | Bad request or unsupported operation. |
| `404` | Device or resource not found. |
| `409` | Device or runtime state conflict. |
| `422` | Request is structurally valid JSON but fails validation. |
| `503` | Runtime, broker, actor, or device temporarily unavailable. |
| `504` | Device command ACK timeout. |

Common error codes:

| Error code | Typical cause |
|---|---|
| `runtime_not_started` | Firefly runtime is not initialized. |
| `broker_unavailable` | MQTT broker is not connected. |
| `device_not_found` | The `deviceName` in the URL is not configured. |
| `actor_not_running` | The device actor is not running. |
| `device_offline` | Device is not active and cannot accept commands. |
| `register_error` | Device is in registration error state. |
| `invalid_external_slot_id` | `externalSlotId` is not configured for the device. |
| `invalid_state_name` | `stateName` does not match a configured LED state. |
| `invalid_pattern` | `pattern` is not one of the supported public pattern names. |
| `empty_slots_list` | `slots:update` was called with no slots. |
| `dynamic_slot_layout_invalid` | `load-slots` request failed layout validation. |
| `firefly_ack_timeout` | Device did not ACK within the configured retry budget. |

## Endpoint Reference

### GET Device Status

Returns current runtime status for a configured Firefly device.

```text
GET /api/v1/public/fireflies/{deviceName}/status
```

Example:

```http
GET /api/v1/public/fireflies/FF01/status HTTP/1.1
Host: firefly-api.local:8000
Accept: application/json
```

Successful response:

```json
{
  "deviceName": "FF01",
  "status": "online",
  "firmwareVersion": "1.0.0",
  "macAddress": "AABBCCDDEEFF",
  "registeredAt": "2026-06-30T10:15:30Z",
  "lastKeepaliveAt": "2026-06-30T10:16:12Z",
  "currentTaskId": "29348e15-e468-4919-ad5c-97576d48ca82"
}
```

Response fields:

| Field | Type | Meaning |
|---|---|---|
| `deviceName` | string | Firefly device name. |
| `status` | string | `unknown`, `online`, `offline`, or `register_error`. |
| `firmwareVersion` | string or null | Last firmware version reported by the device. |
| `macAddress` | string or null | Last MAC address reported by the device. |
| `registeredAt` | string or null | Last successful registration timestamp. |
| `lastKeepaliveAt` | string or null | Last keepalive timestamp. |
| `currentTaskId` | string or null | Current task ID accepted by the device. |

### POST Load Dynamic Slots

Loads or clears the slot layout for one or more dynamic segments on a single Firefly device.

```text
POST /api/v1/public/fireflies/{deviceName}/load-slots
```

Use this endpoint only for segments configured as `dynamic` in the frontend. If any segment in the request is not dynamic, the whole request fails and no layout is changed.

This endpoint:

1. Validates all requested segments and slots.
2. Replaces the slot layout for each requested dynamic segment.
3. Assigns `segment_position` from the array order, starting at `1`.
4. Sets each internal slot label to the same value as `externalSlotId`.
5. Recalculates all device-wide internal `slot-inx` values.
6. Sends a fresh `init-slots` command to the Firefly controller.
7. Waits for the Firefly controller ACK before returning success.

Request example:

```http
POST /api/v1/public/fireflies/FF01/load-slots HTTP/1.1
Host: firefly-api.local:8000
Content-Type: application/json
Accept: application/json

{
  "segments": [
    {
      "channelNum": 2,
      "segmentNumInChannel": 1,
      "slots": [
        { "externalSlotId": "BOX-001", "numLeds": 12 },
        { "externalSlotId": "BOX-002", "numLeds": 18 }
      ]
    },
    {
      "channelNum": 2,
      "segmentNumInChannel": 2,
      "slots": []
    }
  ]
}
```

Successful response:

```json
{
  "deviceName": "FF01",
  "status": "loaded",
  "eventId": "5c563765-8d30-49df-a8cc-dc35066b4f49",
  "currentTaskId": "29348e15-e468-4919-ad5c-97576d48ca82",
  "clientRequestId": null
}
```

Request fields:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `segments` | array | Yes | One or more dynamic segment layouts to load. |

Segment object fields:

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `channelNum` | integer | Yes | `>= 1` | Channel number of the target segment. |
| `segmentNumInChannel` | integer | Yes | `>= 1` | Segment number within the channel. |
| `slots` | array | Yes | Can be empty | New slot layout for this segment. Empty array clears the segment. |

Slot object fields:

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `externalSlotId` | string | Yes | `^[A-Za-z0-9_-]{1,64}$` | Stable public slot identifier used later by `slots:update`. |
| `numLeds` | integer | Yes | `>= 1` | Number of LEDs assigned to this slot. |

Validation rules:

| Rule | Behavior |
|---|---|
| All referenced segments must exist on the device. | Otherwise request fails with `dynamic_slot_layout_invalid`. |
| All referenced segments must be `dynamic`. | Otherwise request fails with `dynamic_slot_layout_invalid`. |
| `externalSlotId` values must be unique across the device. | Otherwise request fails. |
| Sum of `numLeds` for a segment must fit in the physical segment LED count. | Otherwise request fails. |
| The request is all-or-nothing. | If validation fails, no segment layout is changed. |

### POST Update Selected Slots

Updates one or more slots by `externalSlotId`.

```text
POST /api/v1/public/fireflies/{deviceName}/slots:update
```

This endpoint is used for both static and dynamic layouts. It does not change slot geometry. It only changes LED state/pattern for existing slots.

Request example:

```http
POST /api/v1/public/fireflies/FF01/slots:update HTTP/1.1
Host: firefly-api.local:8000
Content-Type: application/json
Accept: application/json

{
  "slots": [
    {
      "externalSlotId": "BOX-001",
      "stateName": "PICK",
      "pattern": "full",
      "patternValue": 0
    },
    {
      "externalSlotId": "BOX-002",
      "stateName": "WAIT",
      "pattern": "slot_ends",
      "patternValue": 0
    }
  ],
  "clientRequestId": "order-123-line-4",
  "timeoutMs": 7000
}
```

Successful response:

```json
{
  "deviceName": "FF01",
  "status": "updated",
  "eventId": "e74142b1-f4df-4910-9f5a-284bdb9cb45d",
  "currentTaskId": "29348e15-e468-4919-ad5c-97576d48ca82",
  "clientRequestId": "order-123-line-4"
}
```

Request fields:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `slots` | array | Yes | One or more slot updates. Must not be empty. |
| `clientRequestId` | string or null | No | Caller correlation ID echoed in the response. |
| `timeoutMs` | integer or null | No | ACK timeout per attempt in milliseconds. If omitted, service default is used. |

Slot update fields:

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `externalSlotId` | string | Yes | None | Stable slot identifier configured or loaded for the device. |
| `stateName` | string | Yes | None | Configured LED state name. |
| `pattern` | string | No | `full` | Public pattern name. |
| `patternValue` | integer | No | `0` | Pattern-specific numeric value. |

### POST Update All Slots

Updates all currently configured slots on a Firefly device to the same state and pattern.

```text
POST /api/v1/public/fireflies/{deviceName}/slots:update-all
```

Request example:

```http
POST /api/v1/public/fireflies/FF01/slots:update-all HTTP/1.1
Host: firefly-api.local:8000
Content-Type: application/json
Accept: application/json

{
  "stateName": "OFF",
  "pattern": "full",
  "patternValue": 0,
  "clientRequestId": "clear-cart-123",
  "timeoutMs": 7000
}
```

Successful response:

```json
{
  "deviceName": "FF01",
  "status": "updated",
  "eventId": "0ae39fc6-1f4d-40fe-9358-93f3a71c7eed",
  "currentTaskId": "29348e15-e468-4919-ad5c-97576d48ca82",
  "clientRequestId": "clear-cart-123"
}
```

Request fields:

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `stateName` | string | Yes | None | Configured LED state name. |
| `pattern` | string | No | `full` | Public pattern name. |
| `patternValue` | integer | No | `0` | Pattern-specific numeric value. |
| `clientRequestId` | string or null | No | `null` | Caller correlation ID echoed in the response. |
| `timeoutMs` | integer or null | No | Service default | ACK timeout per attempt in milliseconds. |

## ACK And Timeout Behavior

The Firefly API Service sends MQTT commands to the Firefly controller and waits for an ACK before returning success for public command endpoints.

The service uses this behavior for:

| Endpoint | MQTT command |
|---|---|
| `load-slots` | `init-slots` |
| `slots:update` | `update-slot-state` |
| `slots:update-all` | `update-all-slots` |

If the device does not ACK in time, the service retries according to its configured retry policy. If all attempts fail, the endpoint returns an error such as `firefly_ack_timeout` and the device may be marked offline.

For `slots:update` and `slots:update-all`, callers may provide `timeoutMs`. This value is the timeout per attempt, not the total wall-clock timeout across all retries.

`load-slots` currently uses the service default ACK timeout.

## Integration Recommendations

1. Treat `externalSlotId` as the customer-facing slot identifier.
2. Do not store or depend on internal `slot-inx` values.
3. For dynamic layouts, call `load-slots` once per device whenever the physical slot layout changes.
4. Wait for `load-slots` success before sending `slots:update` for the newly loaded slots.
5. Keep `externalSlotId` values unique for a device.
6. Use `clientRequestId` on `slots:update` and `slots:update-all` when it helps correlate customer logs with Firefly API logs.
7. Handle `422` responses as integration or configuration errors that usually require correcting request data or frontend configuration.
8. Handle `503` and `504` responses as runtime/device availability problems and retry only according to the customer's operational policy.
9. Use the frontend status page and service logs for troubleshooting device registration, MQTT connectivity, and ACK timeout issues.

## Example Dynamic Picking Cart Sequence

The customer system starts a picking tour and determines that cart device `FF-CART-01` has two boxes on segment channel `2`, segment `1`.

Step 1: Load the dynamic layout.

```http
POST /api/v1/public/fireflies/FF-CART-01/load-slots HTTP/1.1
Host: firefly-api.local:8000
Content-Type: application/json

{
  "segments": [
    {
      "channelNum": 2,
      "segmentNumInChannel": 1,
      "slots": [
        { "externalSlotId": "TOUR-9001-BOX-A", "numLeds": 20 },
        { "externalSlotId": "TOUR-9001-BOX-B", "numLeds": 14 }
      ]
    }
  ]
}
```

Step 2: Light the box that needs attention.

```http
POST /api/v1/public/fireflies/FF-CART-01/slots:update HTTP/1.1
Host: firefly-api.local:8000
Content-Type: application/json

{
  "slots": [
    {
      "externalSlotId": "TOUR-9001-BOX-B",
      "stateName": "PICK",
      "pattern": "full",
      "patternValue": 0
    }
  ],
  "clientRequestId": "tour-9001-step-12"
}
```

Step 3: Clear all slots at the end of the tour.

```http
POST /api/v1/public/fireflies/FF-CART-01/slots:update-all HTTP/1.1
Host: firefly-api.local:8000
Content-Type: application/json

{
  "stateName": "OFF",
  "pattern": "full",
  "patternValue": 0,
  "clientRequestId": "tour-9001-clear"
}
```

Optionally, clear the dynamic layout if those external slot IDs should no longer be valid:

```http
POST /api/v1/public/fireflies/FF-CART-01/load-slots HTTP/1.1
Host: firefly-api.local:8000
Content-Type: application/json

{
  "segments": [
    {
      "channelNum": 2,
      "segmentNumInChannel": 1,
      "slots": []
    }
  ]
}
```

## Change History

| Document version | Date | Notes |
|---|---|---|
| 0.1 | 2026-06-30 | Initial public API integration guide. |
