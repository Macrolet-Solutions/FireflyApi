import { useQueries } from "@tanstack/react-query";
import { api, isApiError } from "@/api/client";
import type { DeviceStatus } from "@/api/types";

/** Fetch status for many devices in parallel. Returns a map keyed by name. */
export function useDeviceStatusesByName(
  names: string[],
): Record<string, DeviceStatus | undefined> {
  const results = useQueries({
    queries: names.map((name) => ({
      queryKey: ["device-status", name],
      queryFn: async () => {
        try {
          return await api.get<DeviceStatus>(
            `/api/v1/public/fireflies/${encodeURIComponent(name)}/status`,
          );
        } catch (e) {
          // If the runtime is not started or the device's actor is not
          // available we want the UI to keep rendering (status: unknown).
          if (isApiError(e)) return undefined;
          throw e;
        }
      },
      refetchInterval: 3000,
    })),
  });
  const map: Record<string, DeviceStatus | undefined> = {};
  results.forEach((r, i) => {
    map[names[i]] = (r.data as DeviceStatus | undefined) ?? undefined;
  });
  return map;
}
