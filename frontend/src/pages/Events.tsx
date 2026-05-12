import {
  Badge,
  Card,
  Group,
  Loader,
  ScrollArea,
  Select,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { useMemo, useState } from "react";
import { useDevices, useEvents } from "@/api/hooks";
import type { FireflyEvent } from "@/api/types";
import { ErrorAlert } from "@/components/ErrorAlert";
import { PageHeader } from "@/components/PageHeader";
import { fmtAbs } from "@/lib/format";

const EVENT_TYPES = [
  "register_request_received",
  "register_response_sent",
  "init_slots_sent",
  "update_slot_state_sent",
  "update_all_slots_sent",
  "reset_sent",
  "ack_received",
  "error_received",
  "keepalive_received",
  "timeout",
  "retry",
];

const COLOR_BY_TYPE: Record<string, string> = {
  register_request_received: "blue",
  register_response_sent: "blue",
  init_slots_sent: "firefly",
  update_slot_state_sent: "firefly",
  update_all_slots_sent: "firefly",
  reset_sent: "yellow",
  ack_received: "teal",
  error_received: "red",
  keepalive_received: "gray",
  timeout: "red",
  retry: "orange",
};

export function Events() {
  const devicesQ = useDevices();
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [eventType, setEventType] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const filters = useMemo(
    () => ({
      deviceId: deviceId ? Number(deviceId) : undefined,
      eventType: eventType ?? undefined,
      limit: 200,
    }),
    [deviceId, eventType],
  );
  const eventsQ = useEvents(filters);

  const deviceNameById: Record<number, string> = {};
  (devicesQ.data ?? []).forEach((d) => {
    deviceNameById[d.id] = d.display_name || d.name;
  });

  return (
    <Stack>
      <PageHeader
        title="Event log"
        description="Insert-only history of every MQTT message and timer event recorded by the actor runtime (§7.7). Polls every 5 s."
      />

      <Card withBorder radius="md" padding="md">
        <Group>
          <Select
            label="Device"
            placeholder="All devices"
            clearable
            data={(devicesQ.data ?? []).map((d) => ({
              value: String(d.id),
              label: d.display_name || d.name,
            }))}
            value={deviceId}
            onChange={setDeviceId}
            style={{ minWidth: 200 }}
          />
          <Select
            label="Event type"
            placeholder="All types"
            clearable
            data={EVENT_TYPES}
            value={eventType}
            onChange={setEventType}
            style={{ minWidth: 240 }}
          />
        </Group>
      </Card>

      <ErrorAlert error={eventsQ.error} />

      <Card withBorder radius="md" padding={0}>
        {eventsQ.isLoading ? (
          <Loader m="md" />
        ) : (
          <ScrollArea h={620}>
            <Table verticalSpacing="xs" stickyHeader>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th style={{ width: 200 }}>When</Table.Th>
                  <Table.Th style={{ width: 90 }}>Device</Table.Th>
                  <Table.Th style={{ width: 220 }}>Type</Table.Th>
                  <Table.Th style={{ width: 110 }}>Event ID</Table.Th>
                  <Table.Th>Detail</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {(eventsQ.data ?? []).length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={5}>
                      <Text c="dimmed" size="sm" ta="center" py="lg">
                        No events match the current filters.
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                )}
                {(eventsQ.data ?? []).map((e) => (
                  <EventRow
                    key={e.id}
                    event={e}
                    deviceLabel={deviceNameById[e.deviceId] ?? `#${e.deviceId}`}
                    expanded={expanded === e.id}
                    onToggle={() =>
                      setExpanded((cur) => (cur === e.id ? null : e.id))
                    }
                  />
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        )}
      </Card>
    </Stack>
  );
}

interface RowProps {
  event: FireflyEvent;
  deviceLabel: string;
  expanded: boolean;
  onToggle: () => void;
}

function EventRow({ event, deviceLabel, expanded, onToggle }: RowProps) {
  const color = COLOR_BY_TYPE[event.eventType] ?? "gray";
  const summary =
    event.errorDescription ||
    (event.taskId ? `task=${event.taskId.slice(0, 8)}…` : "") ||
    "";
  return (
    <>
      <Table.Tr onClick={onToggle} style={{ cursor: "pointer" }}>
        <Table.Td>
          <Text size="xs" c="dimmed">
            {fmtAbs(event.createdAt)}
          </Text>
        </Table.Td>
        <Table.Td>
          <Text size="sm">{deviceLabel}</Text>
        </Table.Td>
        <Table.Td>
          <Badge color={color} variant="light" radius="sm">
            {event.eventType}
          </Badge>
        </Table.Td>
        <Table.Td>
          <Text size="xs" ff="monospace" c="dimmed">
            {event.eventId.slice(0, 8)}…
          </Text>
        </Table.Td>
        <Table.Td>
          <Text size="sm" lineClamp={1}>
            {summary}
          </Text>
        </Table.Td>
      </Table.Tr>
      {expanded && (
        <Table.Tr>
          <Table.Td colSpan={5}>
            <Card withBorder radius="sm" padding="sm" m="xs">
              <Group justify="space-between" mb="xs">
                <Group>
                  <Text size="xs" c="dimmed">
                    full event_id:
                  </Text>
                  <Text size="xs" ff="monospace">
                    {event.eventId}
                  </Text>
                </Group>
                {event.taskId && (
                  <Group>
                    <Text size="xs" c="dimmed">
                      task_id:
                    </Text>
                    <Text size="xs" ff="monospace">
                      {event.taskId}
                    </Text>
                  </Group>
                )}
              </Group>
              {event.errorCode && (
                <Text size="sm" c="red">
                  {event.errorCode}: {event.errorDescription}
                </Text>
              )}
              <pre className="json-block">
                {event.payloadJson
                  ? JSON.stringify(event.payloadJson, null, 2)
                  : "(no payload)"}
              </pre>
            </Card>
          </Table.Td>
        </Table.Tr>
      )}
    </>
  );
}
