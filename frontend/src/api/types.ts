// Backend API types — kept in sync with backend/firefly_api/schemas/*.

export interface MqttBroker {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string | null;
  use_tls: boolean;
  client_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface MqttBrokerCreate {
  name: string;
  host: string;
  port: number;
  username?: string | null;
  password?: string | null;
  use_tls: boolean;
  client_id?: string | null;
}

export interface FireflyDevice {
  id: number;
  name: string;
  display_name: string | null;
  description: string | null;
  mqtt_broker_id: number;
  created_at: string;
  updated_at: string;
}

export interface FireflyDeviceCreate {
  name: string;
  display_name?: string | null;
  description?: string | null;
  mqtt_broker_id: number;
}

export interface FireflySegment {
  id: number;
  device_id: number;
  channel_num: number;
  segment_num_in_channel: number;
  first_led_index: number;
  last_led_index: number;
  created_at: string;
  updated_at: string;
}

export interface FireflySegmentInput {
  channel_num: number;
  segment_num_in_channel: number;
  first_led_index: number;
  last_led_index: number;
}

export interface FireflySlot {
  id: number;
  device_id: number;
  segment_id: number;
  slot_index: number;
  external_slot_id: string;
  label: string | null;
  segment_position: number;
  num_leds: number;
  created_at: string;
  updated_at: string;
}

export interface FireflySlotCreate {
  segment_id: number;
  external_slot_id: string;
  label?: string | null;
  segment_position: number;
  num_leds: number;
}

export interface FireflySlotUpdate {
  external_slot_id: string;
  label?: string | null;
  num_leds: number;
}

export interface FireflyLedState {
  id: number;
  name: string;
  rgb: string;
  color1_on_ms: number;
  color1_fade_up_ms: number;
  color1_fade_down_ms: number;
  repeat_after_ms: number;
  num_repetitions: number;
  created_at: string;
  updated_at: string;
}

export interface FireflyLedStateInput {
  name: string;
  rgb: string;
  color1_on_ms?: number;
  color1_fade_up_ms?: number;
  color1_fade_down_ms?: number;
  repeat_after_ms?: number;
  num_repetitions?: number;
}

export interface FireflyCommandPreset {
  id: number;
  name: string;
  led_state_id: number;
  pattern: number;
  pattern_value: number;
  created_at: string;
  updated_at: string;
}

export interface FireflyCommandPresetInput {
  name: string;
  led_state_id: number;
  pattern: number;
  pattern_value?: number;
}

export type DeviceStatusValue = "unknown" | "online" | "offline" | "register_error";

export interface DeviceStatus {
  deviceName: string;
  status: DeviceStatusValue;
  firmwareVersion: string | null;
  macAddress: string | null;
  registeredAt: string | null;
  lastKeepaliveAt: string | null;
  currentTaskId: string | null;
}

export interface CommandResponse {
  deviceName: string;
  status: string;
  eventId: string;
  currentTaskId: string | null;
  clientRequestId: string | null;
}

export interface ActorLifecycleResponse {
  deviceId: number;
  actorStatus: "started" | "already_running" | "stopped" | "already_stopped";
}

export interface ReinitializeResponse {
  deviceId: number;
  status: string;
  eventId: string;
  currentTaskId: string | null;
}

export interface ResetResponse {
  deviceId: number;
  status: string;
  eventId: string;
}

export interface TestConnectionResult {
  brokerId: number;
  success: boolean;
  connectedAt?: string;
  errorCode?: string;
  errorDescription?: string;
}

export interface FireflyEvent {
  id: number;
  deviceId: number;
  eventId: string;
  eventType: string;
  taskId: string | null;
  payloadJson: Record<string, unknown> | null;
  errorCode: string | null;
  errorDescription: string | null;
  createdAt: string;
}

export const PATTERN_OPTIONS = [
  { value: "full", label: "full (0)" },
  { value: "slot_ends", label: "slot_ends (1)" },
  { value: "slot_no_ends", label: "slot_no_ends (2)" },
  { value: "subsegments", label: "subsegments (3)" },
  { value: "multicolor", label: "multicolor (4)" },
] as const;

export const PATTERN_INT_TO_NAME: Record<number, string> = {
  0: "full",
  1: "slot_ends",
  2: "slot_no_ends",
  3: "subsegments",
  4: "multicolor",
};

export const STATUS_COLORS: Record<DeviceStatusValue, string> = {
  unknown: "gray",
  online: "teal",
  offline: "red",
  register_error: "orange",
};
