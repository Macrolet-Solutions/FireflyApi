import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Group,
  MultiSelect,
  NumberInput,
  Select,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconBolt,
  IconCheck,
  IconPlayerPlay,
  IconWand,
  IconX,
} from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { isApiError } from "@/api/client";
import {
  useDevices,
  useLedStates,
  usePresets,
  useSlots,
  useTestSlots,
} from "@/api/hooks";
import type { CommandResponse } from "@/api/types";
import { PATTERN_OPTIONS } from "@/api/types";
import { ErrorAlert } from "@/components/ErrorAlert";
import { PageHeader } from "@/components/PageHeader";

interface OutcomeRow {
  id: number;
  ok: boolean;
  message: string;
  eventId?: string;
  taskId?: string | null;
  ts: string;
}

export function ManualTest() {
  const devicesQ = useDevices();
  const ledQ = useLedStates();
  const presetsQ = usePresets();

  const [deviceId, setDeviceId] = useState<string | null>(null);
  const slotsQ = useSlots(deviceId ? Number(deviceId) : undefined);
  const test = useTestSlots(deviceId ? Number(deviceId) : 0);

  const [selectedSlots, setSelectedSlots] = useState<string[]>([]);
  const [stateName, setStateName] = useState<string | null>(null);
  const [pattern, setPattern] = useState<string>("full");
  const [patternValue, setPatternValue] = useState<number | "">(0);
  const [timeoutMs, setTimeoutMs] = useState<number | "">(2000);
  const [history, setHistory] = useState<OutcomeRow[]>([]);

  const devices = devicesQ.data ?? [];
  const slots = slotsQ.data ?? [];
  const ledStates = ledQ.data ?? [];
  const presets = presetsQ.data ?? [];

  const slotOptions = useMemo(
    () =>
      slots.map((s) => ({
        value: String(s.id),
        label: `${s.external_slot_id} (idx ${s.slot_index})`,
      })),
    [slots],
  );

  const ledOptions = useMemo(
    () => ledStates.map((s) => ({ value: s.name, label: s.name })),
    [ledStates],
  );

  const applyPreset = (presetId: string | null) => {
    if (!presetId) return;
    const preset = presets.find((p) => String(p.id) === presetId);
    if (!preset) return;
    const ledName = ledStates.find((s) => s.id === preset.led_state_id)?.name;
    if (ledName) setStateName(ledName);
    setPattern(PATTERN_OPTIONS[preset.pattern]?.value ?? "full");
    setPatternValue(preset.pattern_value);
  };

  const handleSend = async () => {
    if (!deviceId || selectedSlots.length === 0 || !stateName) {
      notifications.show({
        color: "yellow",
        title: "Missing input",
        message: "Pick a device, at least one slot, and an LED state.",
      });
      return;
    }
    try {
      const res = await test.mutateAsync({
        slots: selectedSlots.map((id) => ({
          slotId: Number(id),
          stateName,
          pattern,
          patternValue: Number(patternValue) || 0,
        })),
        timeoutMs: Number(timeoutMs) || undefined,
      });
      pushHistory(res, "Slots updated.");
    } catch (e) {
      pushFailure(e);
    }
  };

  const pushHistory = (res: CommandResponse, msg: string) => {
    setHistory((rows) => [
      {
        id: Date.now(),
        ok: true,
        message: msg,
        eventId: res.eventId,
        taskId: res.currentTaskId,
        ts: new Date().toISOString(),
      },
      ...rows.slice(0, 19),
    ]);
  };

  const pushFailure = (e: unknown) => {
    const message = isApiError(e)
      ? `${e.errorCode}: ${e.description}`
      : String(e);
    setHistory((rows) => [
      {
        id: Date.now(),
        ok: false,
        message,
        ts: new Date().toISOString(),
      },
      ...rows.slice(0, 19),
    ]);
    notifications.show({
      color: "red",
      title: "Test slot update failed",
      message,
    });
  };

  return (
    <Stack>
      <PageHeader
        title="Manual test"
        description="Send ad-hoc update-slot-state commands directly to the device. Uses the admin slots:test endpoint (§9.5)."
      />

      <ErrorAlert error={devicesQ.error || ledQ.error || presetsQ.error} />

      <Card withBorder radius="md" padding="lg">
        <Stack>
          <Group grow>
            <Select
              label="Device"
              placeholder="Select a device"
              data={devices.map((d) => ({
                value: String(d.id),
                label: d.display_name || d.name,
              }))}
              value={deviceId}
              onChange={(v) => {
                setDeviceId(v);
                setSelectedSlots([]);
              }}
              required
            />
            <Select
              label="Preset (optional)"
              placeholder="Apply a saved preset"
              data={presets.map((p) => ({
                value: String(p.id),
                label: p.name,
              }))}
              onChange={applyPreset}
              clearable
              leftSection={<IconWand size={14} />}
              description="Sets the LED state + pattern + value fields below."
            />
          </Group>

          <MultiSelect
            label="Slots"
            placeholder={
              deviceId ? "Pick one or more slots" : "Select a device first"
            }
            data={slotOptions}
            value={selectedSlots}
            onChange={setSelectedSlots}
            disabled={!deviceId || slotOptions.length === 0}
            searchable
            description={
              deviceId && slotOptions.length === 0
                ? "This device has no slots configured."
                : undefined
            }
          />

          <Group grow>
            <Select
              label="LED state"
              placeholder="Pick a state"
              data={ledOptions}
              value={stateName}
              onChange={setStateName}
              required
            />
            <Select
              label="Pattern"
              data={PATTERN_OPTIONS as unknown as { value: string; label: string }[]}
              value={pattern}
              onChange={(v) => v && setPattern(v)}
            />
            <NumberInput
              label="Pattern value"
              min={0}
              value={patternValue}
              onChange={(v) =>
                setPatternValue(typeof v === "number" ? v : "")
              }
            />
            <NumberInput
              label="Per-attempt timeout (ms)"
              min={1}
              value={timeoutMs}
              onChange={(v) =>
                setTimeoutMs(typeof v === "number" ? v : "")
              }
            />
          </Group>

          <Group justify="flex-end">
            <Button
              size="md"
              leftSection={<IconPlayerPlay size={16} />}
              onClick={handleSend}
              loading={test.isPending}
              disabled={!deviceId || selectedSlots.length === 0 || !stateName}
            >
              Send
            </Button>
          </Group>
        </Stack>
      </Card>

      <Card withBorder radius="md" padding={0}>
        <Group justify="space-between" p="md">
          <Group gap="xs">
            <IconBolt size={18} />
            <Text fw={600}>Recent outcomes</Text>
          </Group>
          {history.length > 0 && (
            <ActionIcon
              variant="subtle"
              color="gray"
              onClick={() => setHistory([])}
              aria-label="Clear"
            >
              <IconX size={14} />
            </ActionIcon>
          )}
        </Group>
        <Table verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>When</Table.Th>
              <Table.Th>Result</Table.Th>
              <Table.Th>Detail</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {history.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={3}>
                  <Box ta="center" py="md">
                    <Text c="dimmed" size="sm">
                      Outcomes will appear here after you send commands.
                    </Text>
                  </Box>
                </Table.Td>
              </Table.Tr>
            )}
            {history.map((row) => (
              <Table.Tr key={row.id}>
                <Table.Td>
                  <Text size="xs" c="dimmed">
                    {new Date(row.ts).toLocaleTimeString()}
                  </Text>
                </Table.Td>
                <Table.Td>
                  {row.ok ? (
                    <Badge
                      color="teal"
                      variant="light"
                      leftSection={<IconCheck size={12} />}
                    >
                      ACK
                    </Badge>
                  ) : (
                    <Badge
                      color="red"
                      variant="light"
                      leftSection={<IconX size={12} />}
                    >
                      Failed
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{row.message}</Text>
                  {row.eventId && (
                    <Text size="xs" c="dimmed" ff="monospace">
                      event_id={row.eventId.slice(0, 8)}…
                      {row.taskId
                        ? ` · task=${row.taskId.slice(0, 8)}…`
                        : ""}
                    </Text>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  );
}
