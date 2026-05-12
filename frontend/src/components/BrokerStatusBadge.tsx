import { Badge, Group, Loader, Skeleton, Tooltip } from "@mantine/core";
import { IconAntenna, IconAntennaOff } from "@tabler/icons-react";
import { useBrokers } from "@/api/hooks";

export function BrokerStatusBadge() {
  const { data, isLoading } = useBrokers();
  if (isLoading) return <Skeleton height={22} width={120} radius="xl" />;
  const configured = (data ?? []).length > 0;
  return (
    <Tooltip
      label={
        configured
          ? "MQTT broker is configured. Connection state is reflected per device."
          : "No MQTT broker configured. Create one in MQTT Broker settings, then restart the backend."
      }
    >
      <Badge
        size="md"
        radius="sm"
        variant={configured ? "light" : "outline"}
        color={configured ? "teal" : "gray"}
        leftSection={
          configured ? (
            <IconAntenna size={12} />
          ) : (
            <IconAntennaOff size={12} />
          )
        }
      >
        <Group gap={4} wrap="nowrap">
          {configured ? "BROKER CONFIGURED" : "NO BROKER"}
          {isLoading && <Loader size={10} />}
        </Group>
      </Badge>
    </Tooltip>
  );
}
