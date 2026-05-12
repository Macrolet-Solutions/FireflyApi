import { Group, Text } from "@mantine/core";
import type { DeviceStatusValue } from "@/api/types";

interface Props {
  status: DeviceStatusValue;
  label?: boolean;
}

const HUMAN: Record<DeviceStatusValue, string> = {
  unknown: "Unknown",
  online: "Online",
  offline: "Offline",
  register_error: "Register error",
};

export function StatusDot({ status, label = true }: Props) {
  return (
    <Group gap={6} wrap="nowrap">
      <span className={`status-dot ${status}`} aria-hidden />
      {label && (
        <Text size="sm" fw={500}>
          {HUMAN[status]}
        </Text>
      )}
    </Group>
  );
}
