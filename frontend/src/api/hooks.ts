import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  ActorLifecycleResponse,
  CommandResponse,
  DeviceStatus,
  FireflyCommandPreset,
  FireflyCommandPresetInput,
  FireflyDevice,
  FireflyDeviceCreate,
  FireflyEvent,
  FireflyLedState,
  FireflyLedStateInput,
  FireflySegment,
  FireflySegmentInput,
  FireflySlot,
  FireflySlotCreate,
  FireflySlotReplaceRequest,
  FireflySlotUpdate,
  MqttBroker,
  MqttBrokerCreate,
  ReinitializeResponse,
  ResetResponse,
  TestConnectionResult,
} from "@/api/types";

const ADMIN = "/api/v1/admin";
const PUBLIC = "/api/v1/public";

// ----- Brokers -----

export function useBrokers() {
  return useQuery({
    queryKey: ["brokers"],
    queryFn: () => api.get<MqttBroker[]>(`${ADMIN}/mqtt-brokers`),
  });
}

export function useCreateBroker() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MqttBrokerCreate) =>
      api.post<MqttBroker>(`${ADMIN}/mqtt-brokers`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["brokers"] }),
  });
}

export function useUpdateBroker() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: MqttBrokerCreate }) =>
      api.put<MqttBroker>(`${ADMIN}/mqtt-brokers/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["brokers"] }),
  });
}

export function useDeleteBroker() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.del<void>(`${ADMIN}/mqtt-brokers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["brokers"] }),
  });
}

export function useTestBrokerConnection() {
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await fetch(
        `${ADMIN}/mqtt-brokers/${id}:test-connection`,
        { method: "POST" },
      );
      const body = (await res.json()) as TestConnectionResult;
      return body;
    },
  });
}

// ----- Devices -----

export function useDevices() {
  return useQuery({
    queryKey: ["devices"],
    queryFn: () => api.get<FireflyDevice[]>(`${ADMIN}/fireflies`),
  });
}

export function useDevice(id: number | undefined) {
  return useQuery({
    queryKey: ["device", id],
    queryFn: () => api.get<FireflyDevice>(`${ADMIN}/fireflies/${id}`),
    enabled: id !== undefined,
  });
}

export function useCreateDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FireflyDeviceCreate) =>
      api.post<FireflyDevice>(`${ADMIN}/fireflies`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["devices"] }),
  });
}

export function useUpdateDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: FireflyDeviceCreate }) =>
      api.put<FireflyDevice>(`${ADMIN}/fireflies/${id}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      qc.invalidateQueries({ queryKey: ["device", vars.id] });
    },
  });
}

export function useDeleteDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.del<void>(`${ADMIN}/fireflies/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["devices"] }),
  });
}

export function useDeviceStatus(name: string | undefined) {
  return useQuery({
    queryKey: ["device-status", name],
    queryFn: () =>
      api.get<DeviceStatus>(`${PUBLIC}/fireflies/${name}/status`),
    enabled: !!name,
    refetchInterval: 3000,
  });
}

export function useStartActor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: number) =>
      api.post<ActorLifecycleResponse>(
        `${ADMIN}/fireflies/${deviceId}:start-actor`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["device-status"] });
    },
  });
}

export function useStopActor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: number) =>
      api.post<ActorLifecycleResponse>(
        `${ADMIN}/fireflies/${deviceId}:stop-actor`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["device-status"] });
    },
  });
}

export function useReinitialize() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      deviceId,
      timeoutMs,
    }: {
      deviceId: number;
      timeoutMs?: number;
    }) =>
      api.post<ReinitializeResponse>(
        `${ADMIN}/fireflies/${deviceId}:reinitialize`,
        { timeoutMs },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device-status"] }),
  });
}

export function useResetDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: number) =>
      api.post<ResetResponse>(`${ADMIN}/fireflies/${deviceId}:reset`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device-status"] }),
  });
}

// ----- Segments -----

export function useSegments(deviceId: number | undefined) {
  return useQuery({
    queryKey: ["segments", deviceId],
    queryFn: () =>
      api.get<FireflySegment[]>(`${ADMIN}/fireflies/${deviceId}/segments`),
    enabled: deviceId !== undefined,
  });
}

export function useCreateSegment(deviceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FireflySegmentInput) =>
      api.post<FireflySegment>(
        `${ADMIN}/fireflies/${deviceId}/segments`,
        body,
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["segments", deviceId] }),
  });
}

export function useUpdateSegment(deviceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      segmentId,
      body,
    }: {
      segmentId: number;
      body: FireflySegmentInput;
    }) =>
      api.put<FireflySegment>(
        `${ADMIN}/fireflies/${deviceId}/segments/${segmentId}`,
        body,
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["segments", deviceId] }),
  });
}

export function useDeleteSegment(deviceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (segmentId: number) =>
      api.del<void>(
        `${ADMIN}/fireflies/${deviceId}/segments/${segmentId}`,
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["segments", deviceId] }),
  });
}

// ----- Slots -----

export function useSlots(deviceId: number | undefined) {
  return useQuery({
    queryKey: ["slots", deviceId],
    queryFn: () =>
      api.get<FireflySlot[]>(`${ADMIN}/fireflies/${deviceId}/slots`),
    enabled: deviceId !== undefined,
  });
}

export function useCreateSlot(deviceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FireflySlotCreate) =>
      api.post<FireflySlot>(`${ADMIN}/fireflies/${deviceId}/slots`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["slots", deviceId] }),
  });
}

export function useUpdateSlot(deviceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      slotId,
      body,
    }: {
      slotId: number;
      body: FireflySlotUpdate;
    }) =>
      api.put<FireflySlot>(
        `${ADMIN}/fireflies/${deviceId}/slots/${slotId}`,
        body,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["slots", deviceId] }),
  });
}

export function useDeleteSlot(deviceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slotId: number) =>
      api.del<void>(`${ADMIN}/fireflies/${deviceId}/slots/${slotId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["slots", deviceId] }),
  });
}

export function useReplaceSlots(deviceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FireflySlotReplaceRequest) =>
      api.put<FireflySlot[]>(`${ADMIN}/fireflies/${deviceId}/slots:replace`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["slots", deviceId] }),
  });
}

export function useTestSlots(deviceId: number) {
  return useMutation({
    mutationFn: (body: {
      slots: Array<{
        slotId: number;
        stateName: string;
        pattern: string;
        patternValue: number;
      }>;
      timeoutMs?: number;
    }) =>
      api.post<CommandResponse>(
        `${ADMIN}/fireflies/${deviceId}/slots:test`,
        body,
      ),
  });
}

// ----- LED states -----

export function useLedStates() {
  return useQuery({
    queryKey: ["led-states"],
    queryFn: () => api.get<FireflyLedState[]>(`${ADMIN}/led-states`),
  });
}

export function useCreateLedState() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FireflyLedStateInput) =>
      api.post<FireflyLedState>(`${ADMIN}/led-states`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["led-states"] }),
  });
}

export function useUpdateLedState() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number;
      body: FireflyLedStateInput;
    }) => api.put<FireflyLedState>(`${ADMIN}/led-states/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["led-states"] }),
  });
}

export function useDeleteLedState() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.del<void>(`${ADMIN}/led-states/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["led-states"] }),
  });
}

// ----- Command presets -----

export function usePresets() {
  return useQuery({
    queryKey: ["presets"],
    queryFn: () => api.get<FireflyCommandPreset[]>(`${ADMIN}/command-presets`),
  });
}

export function useCreatePreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FireflyCommandPresetInput) =>
      api.post<FireflyCommandPreset>(`${ADMIN}/command-presets`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["presets"] }),
  });
}

export function useUpdatePreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number;
      body: FireflyCommandPresetInput;
    }) => api.put<FireflyCommandPreset>(`${ADMIN}/command-presets/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["presets"] }),
  });
}

export function useDeletePreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      api.del<void>(`${ADMIN}/command-presets/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["presets"] }),
  });
}

// ----- Events -----

export interface EventFilters {
  deviceId?: number;
  eventType?: string;
  beforeId?: number;
  limit?: number;
}

export function useEvents(filters: EventFilters = {}) {
  const qs = new URLSearchParams();
  if (filters.deviceId) qs.set("deviceId", String(filters.deviceId));
  if (filters.eventType) qs.set("eventType", filters.eventType);
  if (filters.beforeId) qs.set("beforeId", String(filters.beforeId));
  if (filters.limit) qs.set("limit", String(filters.limit));
  const qsStr = qs.toString() ? `?${qs.toString()}` : "";
  return useQuery({
    queryKey: ["events", filters],
    queryFn: () => api.get<FireflyEvent[]>(`${ADMIN}/events${qsStr}`),
    refetchInterval: 5000,
  });
}
