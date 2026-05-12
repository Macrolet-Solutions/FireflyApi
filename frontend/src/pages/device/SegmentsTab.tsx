import {
  ActionIcon,
  Button,
  Card,
  Group,
  Modal,
  NumberInput,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { isApiError } from "@/api/client";
import {
  useCreateSegment,
  useDeleteSegment,
  useSegments,
  useUpdateSegment,
} from "@/api/hooks";
import type { FireflySegment } from "@/api/types";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ResetRequiredBanner } from "@/components/ResetRequiredBanner";

interface Props {
  deviceId: number;
}

interface SegmentFormValues {
  channel_num: number | "";
  segment_num_in_channel: number | "";
  first_led_index: number | "";
  last_led_index: number | "";
}

function emptyValues(): SegmentFormValues {
  return {
    channel_num: 1,
    segment_num_in_channel: 1,
    first_led_index: 1,
    last_led_index: 150,
  };
}

export function SegmentsTab({ deviceId }: Props) {
  const q = useSegments(deviceId);
  const create = useCreateSegment(deviceId);
  const update = useUpdateSegment(deviceId);
  const del = useDeleteSegment(deviceId);
  const [editing, setEditing] = useState<FireflySegment | null>(null);
  const [adding, setAdding] = useState(false);

  return (
    <Stack>
      <Group justify="space-between" align="center">
        <div>
          <Title order={4}>Segments</Title>
          <Text size="sm" c="dimmed">
            Physical LED segments wired to the device. Sent to the firmware in
            the registration response.
          </Text>
        </div>
        <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
          Add segment
        </Button>
      </Group>

      <ResetRequiredBanner scope="segments" />

      <ErrorAlert error={q.error} />

      <Card withBorder padding={0} radius="md">
        <Table.ScrollContainer minWidth={600}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>ID</Table.Th>
                <Table.Th>Channel</Table.Th>
                <Table.Th>Segment in channel</Table.Th>
                <Table.Th>First LED</Table.Th>
                <Table.Th>Last LED</Table.Th>
                <Table.Th>LED count</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(q.data ?? []).length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={7}>
                    <Text c="dimmed" size="sm" ta="center" py="lg">
                      No segments configured.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {(q.data ?? []).map((seg) => {
                const ledCount =
                  Math.abs(seg.last_led_index - seg.first_led_index) + 1;
                return (
                  <Table.Tr key={seg.id}>
                    <Table.Td>
                      <Text size="sm" ff="monospace">
                        #{seg.id}
                      </Text>
                    </Table.Td>
                    <Table.Td>{seg.channel_num}</Table.Td>
                    <Table.Td>{seg.segment_num_in_channel}</Table.Td>
                    <Table.Td>{seg.first_led_index}</Table.Td>
                    <Table.Td>{seg.last_led_index}</Table.Td>
                    <Table.Td>{ledCount}</Table.Td>
                    <Table.Td style={{ textAlign: "right" }}>
                      <Group gap="xs" justify="flex-end">
                        <Tooltip label="Edit">
                          <ActionIcon
                            variant="subtle"
                            onClick={() => setEditing(seg)}
                          >
                            <IconPencil size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip label="Delete">
                          <ActionIcon
                            color="red"
                            variant="subtle"
                            onClick={async () => {
                              if (!confirm(`Delete segment #${seg.id}?`)) return;
                              try {
                                await del.mutateAsync(seg.id);
                                notifications.show({
                                  color: "teal",
                                  title: "Segment deleted",
                                  message: `#${seg.id}`,
                                });
                              } catch (e) {
                                notifications.show({
                                  color: "red",
                                  title: "Could not delete segment",
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
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      <SegmentDialog
        opened={adding || !!editing}
        editing={editing}
        onClose={() => {
          setAdding(false);
          setEditing(null);
        }}
        onSubmit={async (vals) => {
          try {
            if (editing) {
              await update.mutateAsync({
                segmentId: editing.id,
                body: vals,
              });
              notifications.show({
                color: "teal",
                title: "Segment updated",
                message: `#${editing.id}`,
              });
            } else {
              await create.mutateAsync(vals);
              notifications.show({
                color: "teal",
                title: "Segment created",
                message: "Remember to reset the device.",
              });
            }
            setAdding(false);
            setEditing(null);
          } catch (e) {
            notifications.show({
              color: "red",
              title: editing ? "Could not update segment" : "Could not create segment",
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
  editing: FireflySegment | null;
  onClose: () => void;
  onSubmit: (vals: {
    channel_num: number;
    segment_num_in_channel: number;
    first_led_index: number;
    last_led_index: number;
  }) => Promise<void>;
}

function SegmentDialog({ opened, editing, onClose, onSubmit }: DialogProps) {
  const form = useForm<SegmentFormValues>({
    initialValues: emptyValues(),
    validate: {
      channel_num: (v) => (typeof v === "number" && v >= 1 ? null : "≥ 1"),
      segment_num_in_channel: (v) =>
        typeof v === "number" && v >= 1 ? null : "≥ 1",
      first_led_index: (v) =>
        typeof v === "number" && v >= 1 ? null : "≥ 1",
      last_led_index: (v) =>
        typeof v === "number" && v >= 1 ? null : "≥ 1",
    },
  });

  useEffect(() => {
    if (!opened) return;
    if (editing) {
      form.setValues({
        channel_num: editing.channel_num,
        segment_num_in_channel: editing.segment_num_in_channel,
        first_led_index: editing.first_led_index,
        last_led_index: editing.last_led_index,
      });
    } else {
      form.setValues(emptyValues());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, editing?.id]);

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={editing ? `Edit segment #${editing.id}` : "Add segment"}
      centered
    >
      <form
        onSubmit={form.onSubmit(async (vals) => {
          await onSubmit({
            channel_num: Number(vals.channel_num),
            segment_num_in_channel: Number(vals.segment_num_in_channel),
            first_led_index: Number(vals.first_led_index),
            last_led_index: Number(vals.last_led_index),
          });
        })}
      >
        <Stack>
          <NumberInput
            label="Channel"
            min={1}
            {...form.getInputProps("channel_num")}
          />
          <NumberInput
            label="Segment in channel"
            min={1}
            {...form.getInputProps("segment_num_in_channel")}
          />
          <NumberInput
            label="First LED index"
            min={1}
            description="1-based inclusive."
            {...form.getInputProps("first_led_index")}
          />
          <NumberInput
            label="Last LED index"
            min={1}
            description="May be lower than first to express reverse growth direction (§6.3)."
            {...form.getInputProps("last_led_index")}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit">
              {editing ? "Save changes" : "Create segment"}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
