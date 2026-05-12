import {
  ActionIcon,
  Button,
  Card,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { isApiError } from "@/api/client";
import {
  useCreatePreset,
  useDeletePreset,
  useLedStates,
  usePresets,
  useUpdatePreset,
} from "@/api/hooks";
import type { FireflyCommandPreset } from "@/api/types";
import { PATTERN_OPTIONS } from "@/api/types";
import { ErrorAlert } from "@/components/ErrorAlert";
import { PageHeader } from "@/components/PageHeader";

interface PresetFormValues {
  name: string;
  led_state_id: string;
  pattern: string;
  pattern_value: number | "";
}

const EMPTY: PresetFormValues = {
  name: "",
  led_state_id: "",
  pattern: "full",
  pattern_value: 0,
};

const PATTERN_INT_BY_NAME = Object.fromEntries(
  PATTERN_OPTIONS.map((p, i) => [p.value, i]),
) as Record<string, number>;

export function Presets() {
  const presetsQ = usePresets();
  const ledQ = useLedStates();
  const create = useCreatePreset();
  const update = useUpdatePreset();
  const del = useDeletePreset();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<FireflyCommandPreset | null>(null);

  const ledStates = ledQ.data ?? [];
  const nameOf = (id: number) =>
    ledStates.find((s) => s.id === id)?.name ?? `#${id}`;

  return (
    <Stack>
      <PageHeader
        title="Command presets"
        description="Friendly names for (state + pattern + pattern-value) combinations used in the manual test panel."
        right={
          <Button
            leftSection={<IconPlus size={16} />}
            disabled={ledStates.length === 0}
            onClick={() => setAdding(true)}
          >
            Add preset
          </Button>
        }
      />

      <ErrorAlert error={presetsQ.error || ledQ.error} />

      <Card withBorder padding={0} radius="md">
        <Table.ScrollContainer minWidth={700}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>LED state</Table.Th>
                <Table.Th>Pattern</Table.Th>
                <Table.Th>Pattern value</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(presetsQ.data ?? []).length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={5}>
                    <Text c="dimmed" size="sm" ta="center" py="lg">
                      No command presets configured.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {(presetsQ.data ?? []).map((p) => (
                <Table.Tr key={p.id}>
                  <Table.Td>
                    <Text fw={500}>{p.name}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{nameOf(p.led_state_id)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {PATTERN_OPTIONS[p.pattern]?.value ?? p.pattern} ({p.pattern})
                    </Text>
                  </Table.Td>
                  <Table.Td>{p.pattern_value}</Table.Td>
                  <Table.Td style={{ textAlign: "right" }}>
                    <Group gap="xs" justify="flex-end">
                      <Tooltip label="Edit">
                        <ActionIcon
                          variant="subtle"
                          onClick={() => setEditing(p)}
                        >
                          <IconPencil size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label="Delete">
                        <ActionIcon
                          color="red"
                          variant="subtle"
                          onClick={async () => {
                            if (!confirm(`Delete preset "${p.name}"?`)) return;
                            try {
                              await del.mutateAsync(p.id);
                              notifications.show({
                                color: "teal",
                                title: "Preset deleted",
                                message: p.name,
                              });
                            } catch (e) {
                              notifications.show({
                                color: "red",
                                title: "Could not delete preset",
                                message: isApiError(e) ? e.description : String(e),
                              });
                            }
                          }}
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      <PresetDialog
        opened={adding || !!editing}
        editing={editing}
        ledOptions={ledStates.map((s) => ({
          value: String(s.id),
          label: s.name,
        }))}
        onClose={() => {
          setAdding(false);
          setEditing(null);
        }}
        onSubmit={async (vals) => {
          try {
            if (editing) {
              await update.mutateAsync({ id: editing.id, body: vals });
              notifications.show({
                color: "teal",
                title: "Preset updated",
                message: vals.name,
              });
            } else {
              await create.mutateAsync(vals);
              notifications.show({
                color: "teal",
                title: "Preset created",
                message: vals.name,
              });
            }
            setAdding(false);
            setEditing(null);
          } catch (e) {
            notifications.show({
              color: "red",
              title: editing ? "Could not update preset" : "Could not create preset",
              message: isApiError(e) ? e.description : String(e),
            });
          }
        }}
      />
    </Stack>
  );
}

interface DialogProps {
  opened: boolean;
  editing: FireflyCommandPreset | null;
  ledOptions: { value: string; label: string }[];
  onClose: () => void;
  onSubmit: (vals: {
    name: string;
    led_state_id: number;
    pattern: number;
    pattern_value: number;
  }) => Promise<void>;
}

function PresetDialog({
  opened,
  editing,
  ledOptions,
  onClose,
  onSubmit,
}: DialogProps) {
  const form = useForm<PresetFormValues>({
    initialValues: EMPTY,
    validate: {
      name: (v) => (v.trim() ? null : "Required"),
      led_state_id: (v) => (v ? null : "Required"),
    },
  });

  useEffect(() => {
    if (!opened) return;
    if (editing) {
      const patternName =
        PATTERN_OPTIONS[editing.pattern]?.value ?? "full";
      form.setValues({
        name: editing.name,
        led_state_id: String(editing.led_state_id),
        pattern: patternName,
        pattern_value: editing.pattern_value,
      });
    } else {
      form.setValues({
        ...EMPTY,
        led_state_id: ledOptions[0]?.value ?? "",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, editing?.id]);

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={editing ? `Edit preset "${editing.name}"` : "Add preset"}
      centered
    >
      <form
        onSubmit={form.onSubmit(async (v) => {
          await onSubmit({
            name: v.name.trim(),
            led_state_id: Number(v.led_state_id),
            pattern: PATTERN_INT_BY_NAME[v.pattern] ?? 0,
            pattern_value: Number(v.pattern_value),
          });
        })}
      >
        <Stack>
          <TextInput label="Name" required {...form.getInputProps("name")} />
          <Select
            label="LED state"
            data={ledOptions}
            required
            {...form.getInputProps("led_state_id")}
          />
          <Select
            label="Pattern"
            data={PATTERN_OPTIONS as unknown as { value: string; label: string }[]}
            {...form.getInputProps("pattern")}
          />
          <NumberInput
            label="Pattern value"
            min={0}
            description="Opaque integer; meaning depends on the firmware's interpretation of the chosen pattern."
            {...form.getInputProps("pattern_value")}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit">{editing ? "Save changes" : "Create"}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
