import {
  ActionIcon,
  Badge,
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
  Title,
  Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { isApiError } from "@/api/client";
import {
  useCreateSlot,
  useDeleteSlot,
  useSegments,
  useSlots,
  useUpdateSlot,
} from "@/api/hooks";
import type { FireflySlot } from "@/api/types";
import { ErrorAlert } from "@/components/ErrorAlert";

interface Props {
  deviceId: number;
}

const EXTERNAL_RE = /^[A-Za-z0-9_-]{1,64}$/;

interface SlotCreateForm {
  segment_id: string;
  external_slot_id: string;
  label: string;
  segment_position: number | "";
  num_leds: number | "";
}

interface SlotEditForm {
  external_slot_id: string;
  label: string;
  num_leds: number | "";
}

export function SlotsTab({ deviceId }: Props) {
  const segmentsQ = useSegments(deviceId);
  const slotsQ = useSlots(deviceId);
  const create = useCreateSlot(deviceId);
  const update = useUpdateSlot(deviceId);
  const del = useDeleteSlot(deviceId);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<FireflySlot | null>(null);

  const segments = segmentsQ.data ?? [];
  const slots = slotsQ.data ?? [];
  const segmentLabel = (id: number) => {
    const seg = segments.find((s) => s.id === id);
    return seg
      ? `ch ${seg.channel_num} · seg ${seg.segment_num_in_channel}`
      : `#${id}`;
  };

  return (
    <Stack>
      <Group justify="space-between" align="center">
        <div>
          <Title order={4}>Slots</Title>
          <Text size="sm" c="dimmed">
            Logical addressable slots within segments. Sent to the firmware via{" "}
            <code>init-slots</code>.
          </Text>
        </div>
        <Button
          leftSection={<IconPlus size={16} />}
          onClick={() => setAdding(true)}
          disabled={segments.length === 0}
        >
          Add slot
        </Button>
      </Group>

      {segments.length === 0 && (
        <Card withBorder radius="md" mb="md">
          <Text size="sm" c="dimmed">
            Add at least one segment before configuring slots.
          </Text>
        </Card>
      )}

      <ErrorAlert error={segmentsQ.error || slotsQ.error} />

      <Card withBorder padding={0} radius="md">
        <Table.ScrollContainer minWidth={700}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>slot_index</Table.Th>
                <Table.Th>External slot id</Table.Th>
                <Table.Th>Segment</Table.Th>
                <Table.Th>Position</Table.Th>
                <Table.Th>LEDs</Table.Th>
                <Table.Th>Label</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {slots.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={7}>
                    <Text c="dimmed" size="sm" ta="center" py="lg">
                      No slots configured.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {slots.map((slot) => (
                <Table.Tr key={slot.id}>
                  <Table.Td>
                    <Badge variant="default">#{slot.slot_index}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {slot.external_slot_id}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{segmentLabel(slot.segment_id)}</Text>
                  </Table.Td>
                  <Table.Td>{slot.segment_position}</Table.Td>
                  <Table.Td>{slot.num_leds}</Table.Td>
                  <Table.Td>
                    <Text size="sm">{slot.label || "—"}</Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: "right" }}>
                    <Group gap="xs" justify="flex-end">
                      <Tooltip label="Edit">
                        <ActionIcon
                          variant="subtle"
                          onClick={() => setEditing(slot)}
                        >
                          <IconPencil size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label="Delete">
                        <ActionIcon
                          color="red"
                          variant="subtle"
                          onClick={async () => {
                            if (
                              !confirm(
                                `Delete slot "${slot.external_slot_id}"?`,
                              )
                            ) {
                              return;
                            }
                            try {
                              await del.mutateAsync(slot.id);
                              notifications.show({
                                color: "teal",
                                title: "Slot deleted",
                                message: slot.external_slot_id,
                              });
                            } catch (e) {
                              notifications.show({
                                color: "red",
                                title: "Could not delete slot",
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

      <SlotCreateDialog
        opened={adding}
        onClose={() => setAdding(false)}
        segments={segments.map((s) => ({
          value: String(s.id),
          label: segmentLabel(s.id),
        }))}
        onSubmit={async (vals) => {
          try {
            await create.mutateAsync(vals);
            notifications.show({
              color: "teal",
              title: "Slot created",
              message: vals.external_slot_id,
            });
            setAdding(false);
          } catch (e) {
            notifications.show({
              color: "red",
              title: "Could not create slot",
              message: isApiError(e) ? e.description : String(e),
            });
          }
        }}
      />

      <SlotEditDialog
        editing={editing}
        onClose={() => setEditing(null)}
        onSubmit={async (vals) => {
          if (!editing) return;
          try {
            await update.mutateAsync({
              slotId: editing.id,
              body: vals,
            });
            notifications.show({
              color: "teal",
              title: "Slot updated",
              message: vals.external_slot_id,
            });
            setEditing(null);
          } catch (e) {
            notifications.show({
              color: "red",
              title: "Could not update slot",
              message: isApiError(e) ? e.description : String(e),
            });
          }
        }}
      />
    </Stack>
  );
}

interface CreateDialogProps {
  opened: boolean;
  onClose: () => void;
  segments: { value: string; label: string }[];
  onSubmit: (vals: {
    segment_id: number;
    external_slot_id: string;
    label: string | null;
    segment_position: number;
    num_leds: number;
  }) => Promise<void>;
}

function SlotCreateDialog({
  opened,
  onClose,
  segments,
  onSubmit,
}: CreateDialogProps) {
  const form = useForm<SlotCreateForm>({
    initialValues: {
      segment_id: segments[0]?.value ?? "",
      external_slot_id: "",
      label: "",
      segment_position: 1,
      num_leds: 10,
    },
    validate: {
      segment_id: (v) => (v ? null : "Required"),
      external_slot_id: (v) =>
        EXTERNAL_RE.test(v) ? null : "1-64 chars: A-Z a-z 0-9 _ -",
      segment_position: (v) =>
        typeof v === "number" && v >= 1 ? null : "≥ 1",
      num_leds: (v) => (typeof v === "number" && v >= 1 ? null : "≥ 1"),
    },
  });

  useEffect(() => {
    if (opened) {
      form.setValues({
        segment_id: segments[0]?.value ?? "",
        external_slot_id: "",
        label: "",
        segment_position: 1,
        num_leds: 10,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  return (
    <Modal opened={opened} onClose={onClose} title="Add slot" centered>
      <form
        onSubmit={form.onSubmit(async (v) => {
          await onSubmit({
            segment_id: Number(v.segment_id),
            external_slot_id: v.external_slot_id.trim(),
            label: v.label.trim() || null,
            segment_position: Number(v.segment_position),
            num_leds: Number(v.num_leds),
          });
        })}
      >
        <Stack>
          <Select
            label="Segment"
            data={segments}
            required
            {...form.getInputProps("segment_id")}
          />
          <TextInput
            label="External slot ID"
            placeholder="SLOT-001"
            description="Used by integrators. Pattern: [A-Za-z0-9_-]{1,64}."
            required
            {...form.getInputProps("external_slot_id")}
          />
          <TextInput
            label="Label"
            placeholder="Optional human-readable label"
            {...form.getInputProps("label")}
          />
          <NumberInput
            label="Segment position"
            min={1}
            description="1-based relative slot order."
            {...form.getInputProps("segment_position")}
          />
          <NumberInput
            label="Number of LEDs"
            min={1}
            {...form.getInputProps("num_leds")}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit">Create</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

interface EditDialogProps {
  editing: FireflySlot | null;
  onClose: () => void;
  onSubmit: (vals: {
    external_slot_id: string;
    label: string | null;
    num_leds: number;
  }) => Promise<void>;
}

function SlotEditDialog({ editing, onClose, onSubmit }: EditDialogProps) {
  const form = useForm<SlotEditForm>({
    initialValues: { external_slot_id: "", label: "", num_leds: 1 },
    validate: {
      external_slot_id: (v) =>
        EXTERNAL_RE.test(v) ? null : "1-64 chars: A-Z a-z 0-9 _ -",
      num_leds: (v) => (typeof v === "number" && v >= 1 ? null : "≥ 1"),
    },
  });

  useEffect(() => {
    if (editing) {
      form.setValues({
        external_slot_id: editing.external_slot_id,
        label: editing.label ?? "",
        num_leds: editing.num_leds,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing?.id]);

  return (
    <Modal
      opened={!!editing}
      onClose={onClose}
      title={editing ? `Edit slot ${editing.external_slot_id}` : ""}
      centered
    >
      <form
        onSubmit={form.onSubmit(async (v) => {
          await onSubmit({
            external_slot_id: v.external_slot_id.trim(),
            label: v.label.trim() || null,
            num_leds: Number(v.num_leds),
          });
        })}
      >
        <Stack>
          <TextInput
            label="External slot ID"
            description="Pattern: [A-Za-z0-9_-]{1,64}."
            required
            {...form.getInputProps("external_slot_id")}
          />
          <TextInput label="Label" {...form.getInputProps("label")} />
          <NumberInput
            label="Number of LEDs"
            min={1}
            {...form.getInputProps("num_leds")}
          />
          <Text size="xs" c="dimmed">
            <code>segment</code>, <code>segment_position</code> and{" "}
            <code>slot_index</code> are immutable. Delete and recreate to move
            a slot.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit">Save</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
