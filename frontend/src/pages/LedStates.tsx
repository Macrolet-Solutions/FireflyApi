import {
  ActionIcon,
  Button,
  Card,
  ColorSwatch,
  Group,
  Modal,
  NumberInput,
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
  useCreateLedState,
  useDeleteLedState,
  useLedStates,
  useUpdateLedState,
} from "@/api/hooks";
import type { FireflyLedState } from "@/api/types";
import { ErrorAlert } from "@/components/ErrorAlert";
import { PageHeader } from "@/components/PageHeader";
import { ResetRequiredBanner } from "@/components/ResetRequiredBanner";

const HEX_RE = /^0x[0-9A-Fa-f]{6}$/;

interface LedStateFormValues {
  name: string;
  rgb: string;
  color1_on_ms: number | "";
  color1_fade_up_ms: number | "";
  color1_fade_down_ms: number | "";
  repeat_after_ms: number | "";
  num_repetitions: number | "";
}

const EMPTY: LedStateFormValues = {
  name: "",
  rgb: "0xFFFFFF",
  color1_on_ms: 0,
  color1_fade_up_ms: 0,
  color1_fade_down_ms: 0,
  repeat_after_ms: 0,
  num_repetitions: 0,
};

function hexFromRgb(rgb: string): string {
  return rgb.startsWith("0x") ? `#${rgb.slice(2)}` : rgb;
}

export function LedStates() {
  const q = useLedStates();
  const create = useCreateLedState();
  const update = useUpdateLedState();
  const del = useDeleteLedState();
  const [editing, setEditing] = useState<FireflyLedState | null>(null);
  const [adding, setAdding] = useState(false);

  return (
    <Stack>
      <PageHeader
        title="LED states"
        description="Reusable low-level Firefly states (color + timing). Sent to devices in the registration response."
        right={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
            Add LED state
          </Button>
        }
      />
      <ResetRequiredBanner scope="led-states" />
      <ErrorAlert error={q.error} />

      <Card withBorder padding={0} radius="md">
        <Table.ScrollContainer minWidth={700}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th />
                <Table.Th>Name</Table.Th>
                <Table.Th>RGB</Table.Th>
                <Table.Th>On (ms)</Table.Th>
                <Table.Th>Fade up</Table.Th>
                <Table.Th>Fade down</Table.Th>
                <Table.Th>Repeat after</Table.Th>
                <Table.Th>Reps</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(q.data ?? []).length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={9}>
                    <Text c="dimmed" size="sm" ta="center" py="lg">
                      No LED states configured. Devices cannot register until at
                      least one exists (§5.3).
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {(q.data ?? []).map((s) => (
                <Table.Tr key={s.id}>
                  <Table.Td>
                    <ColorSwatch color={hexFromRgb(s.rgb)} size={20} />
                  </Table.Td>
                  <Table.Td>
                    <Text fw={500}>{s.name}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {s.rgb}
                    </Text>
                  </Table.Td>
                  <Table.Td>{s.color1_on_ms}</Table.Td>
                  <Table.Td>{s.color1_fade_up_ms}</Table.Td>
                  <Table.Td>{s.color1_fade_down_ms}</Table.Td>
                  <Table.Td>{s.repeat_after_ms}</Table.Td>
                  <Table.Td>{s.num_repetitions}</Table.Td>
                  <Table.Td style={{ textAlign: "right" }}>
                    <Group gap="xs" justify="flex-end">
                      <Tooltip label="Edit">
                        <ActionIcon
                          variant="subtle"
                          onClick={() => setEditing(s)}
                        >
                          <IconPencil size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label="Delete">
                        <ActionIcon
                          color="red"
                          variant="subtle"
                          onClick={async () => {
                            if (!confirm(`Delete LED state "${s.name}"?`)) return;
                            try {
                              await del.mutateAsync(s.id);
                              notifications.show({
                                color: "teal",
                                title: "LED state deleted",
                                message: s.name,
                              });
                            } catch (e) {
                              notifications.show({
                                color: "red",
                                title: "Could not delete LED state",
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

      <LedStateDialog
        opened={adding || !!editing}
        editing={editing}
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
                title: "LED state updated",
                message: vals.name,
              });
            } else {
              await create.mutateAsync(vals);
              notifications.show({
                color: "teal",
                title: "LED state created",
                message: "Remember to reset devices.",
              });
            }
            setAdding(false);
            setEditing(null);
          } catch (e) {
            notifications.show({
              color: "red",
              title: editing ? "Could not update LED state" : "Could not create LED state",
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
  editing: FireflyLedState | null;
  onClose: () => void;
  onSubmit: (vals: {
    name: string;
    rgb: string;
    color1_on_ms: number;
    color1_fade_up_ms: number;
    color1_fade_down_ms: number;
    repeat_after_ms: number;
    num_repetitions: number;
  }) => Promise<void>;
}

function LedStateDialog({ opened, editing, onClose, onSubmit }: DialogProps) {
  const form = useForm<LedStateFormValues>({
    initialValues: EMPTY,
    validate: {
      name: (v) => (v.trim() ? null : "Required"),
      rgb: (v) =>
        HEX_RE.test(v) ? null : "Format: 0xRRGGBB (uppercase or lowercase).",
    },
  });

  useEffect(() => {
    if (!opened) return;
    if (editing) {
      form.setValues({
        name: editing.name,
        rgb: editing.rgb,
        color1_on_ms: editing.color1_on_ms,
        color1_fade_up_ms: editing.color1_fade_up_ms,
        color1_fade_down_ms: editing.color1_fade_down_ms,
        repeat_after_ms: editing.repeat_after_ms,
        num_repetitions: editing.num_repetitions,
      });
    } else {
      form.setValues(EMPTY);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, editing?.id]);

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={editing ? `Edit LED state "${editing.name}"` : "Add LED state"}
      centered
      size="lg"
    >
      <form
        onSubmit={form.onSubmit(async (v) => {
          await onSubmit({
            name: v.name.trim(),
            rgb: v.rgb.trim(),
            color1_on_ms: Number(v.color1_on_ms),
            color1_fade_up_ms: Number(v.color1_fade_up_ms),
            color1_fade_down_ms: Number(v.color1_fade_down_ms),
            repeat_after_ms: Number(v.repeat_after_ms),
            num_repetitions: Number(v.num_repetitions),
          });
        })}
      >
        <Stack>
          <Group grow align="flex-start">
            <TextInput
              label="Name"
              required
              {...form.getInputProps("name")}
            />
            <Group align="flex-end" gap="xs">
              <TextInput
                label="RGB"
                placeholder="0xFFFFFF"
                style={{ flex: 1 }}
                {...form.getInputProps("rgb")}
              />
              <ColorSwatch
                color={
                  HEX_RE.test(form.values.rgb)
                    ? hexFromRgb(form.values.rgb)
                    : "#888"
                }
                size={36}
                style={{ alignSelf: "flex-end" }}
              />
            </Group>
          </Group>
          <Group grow>
            <NumberInput
              label="Color1 on (ms)"
              min={0}
              {...form.getInputProps("color1_on_ms")}
            />
            <NumberInput
              label="Color1 fade up (ms)"
              min={0}
              {...form.getInputProps("color1_fade_up_ms")}
            />
            <NumberInput
              label="Color1 fade down (ms)"
              min={0}
              {...form.getInputProps("color1_fade_down_ms")}
            />
          </Group>
          <Group grow>
            <NumberInput
              label="Repeat after (ms)"
              min={0}
              {...form.getInputProps("repeat_after_ms")}
            />
            <NumberInput
              label="Number of repetitions"
              min={0}
              {...form.getInputProps("num_repetitions")}
            />
          </Group>
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
