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
import {
  IconDownload,
  IconPencil,
  IconPlus,
  IconTrash,
  IconUpload,
} from "@tabler/icons-react";
import { readSheet } from "read-excel-file/browser";
import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import writeXlsxFile, { type SheetData } from "write-excel-file/browser";
import { isApiError } from "@/api/client";
import {
  useCreateSlot,
  useDeleteSlot,
  useReplaceSlots,
  useSegments,
  useSlots,
  useUpdateSlot,
} from "@/api/hooks";
import type {
  FireflySegment,
  FireflySlot,
  FireflySlotImportRow,
} from "@/api/types";
import { ErrorAlert } from "@/components/ErrorAlert";
import {
  SortableTableHeader,
  type SortDirection,
} from "@/components/SortableTableHeader";

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

type SlotSortKey =
  | "slot_index"
  | "external_slot_id"
  | "segment_id"
  | "segment_position"
  | "num_leds"
  | "label";

const SLOT_COLUMNS: { key: SlotSortKey; label: string }[] = [
  { key: "slot_index", label: "slot_index" },
  { key: "external_slot_id", label: "External slot id" },
  { key: "segment_id", label: "Segment" },
  { key: "segment_position", label: "Position" },
  { key: "num_leds", label: "LEDs" },
  { key: "label", label: "Label" },
];

const SLOT_WORKBOOK_HEADERS = [
  "external_slot_id",
  "label",
  "channel_num",
  "segment_num_in_channel",
  "segment_position",
  "num_leds",
] as const;

function compareSlotValues(
  aValue: number | string | null,
  bValue: number | string | null,
) {
  if (typeof aValue === "number" && typeof bValue === "number") {
    return aValue - bValue;
  }

  return String(aValue ?? "").localeCompare(String(bValue ?? ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function buildSlotsWorkbookData(
  slots: FireflySlot[],
  segments: FireflySegment[],
): SheetData {
  const segmentById = new Map(segments.map((segment) => [segment.id, segment]));
  const rows = [...slots]
    .sort((a, b) => a.slot_index - b.slot_index)
    .map((slot) => {
      const segment = segmentById.get(slot.segment_id);
      return [
        slot.external_slot_id,
        slot.label ?? "",
        segment?.channel_num ?? "",
        segment?.segment_num_in_channel ?? "",
        slot.segment_position,
        slot.num_leds,
      ];
    });

  return [[...SLOT_WORKBOOK_HEADERS], ...rows];
}

function workbookCellText(value: unknown) {
  return value == null ? "" : String(value).trim();
}

function parsePositiveInt(value: unknown, rowNumber: number, field: string) {
  const text = workbookCellText(value);
  if (!/^\d+$/.test(text) || Number(text) < 1) {
    throw new Error(`Row ${rowNumber}: ${field} must be a positive integer.`);
  }
  return Number(text);
}

function parseSlotWorkbookRows(rows: unknown[][]): FireflySlotImportRow[] {
  const nonEmptyRows = rows.filter((row) =>
    row.some((item) => workbookCellText(item) !== ""),
  );
  if (nonEmptyRows.length === 0) throw new Error("Workbook is empty.");

  const headers = nonEmptyRows[0].map((header, index) =>
    (index === 0
      ? workbookCellText(header).replace(/^\uFEFF/, "")
      : workbookCellText(header)),
  );
  const expectedHeaders = [...SLOT_WORKBOOK_HEADERS];
  if (headers.join(",") !== expectedHeaders.join(",")) {
    throw new Error(`Workbook headers must be: ${expectedHeaders.join(",")}.`);
  }

  return nonEmptyRows.slice(1).map((row, index) => {
    const rowNumber = index + 2;
    if (row.length !== expectedHeaders.length) {
      throw new Error(`Row ${rowNumber}: expected ${expectedHeaders.length} columns.`);
    }

    const externalSlotId = workbookCellText(row[0]);
    if (!EXTERNAL_RE.test(externalSlotId)) {
      throw new Error(`Row ${rowNumber}: external_slot_id is invalid.`);
    }

    const label = workbookCellText(row[1]);
    return {
      external_slot_id: externalSlotId,
      label: label || null,
      channel_num: parsePositiveInt(row[2], rowNumber, "channel_num"),
      segment_num_in_channel: parsePositiveInt(
        row[3],
        rowNumber,
        "segment_num_in_channel",
      ),
      segment_position: parsePositiveInt(row[4], rowNumber, "segment_position"),
      num_leds: parsePositiveInt(row[5], rowNumber, "num_leds"),
    };
  });
}

function importErrorMessage(error: unknown) {
  if (!isApiError(error)) return String(error);
  const errors = error.details.errors;
  if (!Array.isArray(errors) || errors.length === 0) return error.description;
  const first = errors[0] as { row?: number; message?: string };
  return first.row
    ? `Row ${first.row}: ${first.message}`
    : first.message ?? error.description;
}

export function SlotsTab({ deviceId }: Props) {
  const segmentsQ = useSegments(deviceId);
  const slotsQ = useSlots(deviceId);
  const create = useCreateSlot(deviceId);
  const update = useUpdateSlot(deviceId);
  const del = useDeleteSlot(deviceId);
  const replace = useReplaceSlots(deviceId);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<FireflySlot | null>(null);
  const [segmentFilter, setSegmentFilter] = useState<string | null>(null);
  const [sort, setSort] = useState<{
    key: SlotSortKey;
    direction: SortDirection;
  }>({ key: "slot_index", direction: "asc" });

  const segments = segmentsQ.data ?? [];
  const slots = slotsQ.data ?? [];
  const segmentLabel = (id: number) => {
    const seg = segments.find((s) => s.id === id);
    return seg
      ? `ch ${seg.channel_num} · seg ${seg.segment_num_in_channel}`
      : `#${id}`;
  };
  const segmentOptions = segments.map((seg) => ({
    value: String(seg.id),
    label: segmentLabel(seg.id),
  }));
  const visibleSlots = useMemo(() => {
    const filtered = segmentFilter
      ? slots.filter((slot) => slot.segment_id === Number(segmentFilter))
      : slots;

    return [...filtered].sort((a, b) => {
      const aValue =
        sort.key === "segment_id" ? segmentLabel(a.segment_id) : a[sort.key];
      const bValue =
        sort.key === "segment_id" ? segmentLabel(b.segment_id) : b[sort.key];
      const result = compareSlotValues(aValue, bValue);
      return sort.direction === "asc" ? result : -result;
    });
  }, [segmentFilter, segments, slots, sort]);

  const setSortKey = (key: SlotSortKey) => {
    setSort((current) => ({
      key,
      direction:
        current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  };

  const handleExport = async () => {
    try {
      await writeXlsxFile(buildSlotsWorkbookData(slots, segments), {
        sheet: "Slots",
        columns: [
          { width: 24 },
          { width: 24 },
          { width: 14 },
          { width: 24 },
          { width: 18 },
          { width: 12 },
        ],
      }).toFile(`firefly-${deviceId}-slots.xlsx`);
    } catch (error) {
      notifications.show({
        color: "red",
        title: "Could not export slots",
        message: String(error),
      });
    }
  };

  const handleImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;

    try {
      const parsedSlots = parseSlotWorkbookRows(await readSheet(file));
      if (
        !confirm(
          `Replace all current slots with ${parsedSlots.length} slots from ${file.name}?`,
        )
      ) {
        return;
      }
      const imported = await replace.mutateAsync({ slots: parsedSlots });
      notifications.show({
        color: "teal",
        title: "Slots imported",
        message: `${imported.length} slots loaded.`,
      });
    } catch (error) {
      notifications.show({
        color: "red",
        title: "Could not import slots",
        message: importErrorMessage(error),
      });
    }
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
        <Group gap="xs">
          <Button
            variant="default"
            leftSection={<IconDownload size={16} />}
            onClick={() => void handleExport()}
          >
            Export XLSX
          </Button>
          <Button
            variant="default"
            leftSection={<IconUpload size={16} />}
            onClick={() => fileInputRef.current?.click()}
            disabled={segments.length === 0 || replace.isPending}
          >
            Import XLSX
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            style={{ display: "none" }}
            onChange={handleImport}
          />
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={() => setAdding(true)}
            disabled={segments.length === 0}
          >
            Add slot
          </Button>
        </Group>
      </Group>

      {segments.length === 0 && (
        <Card withBorder radius="md" mb="md">
          <Text size="sm" c="dimmed">
            Add at least one segment before configuring slots.
          </Text>
        </Card>
      )}

      <ErrorAlert error={segmentsQ.error || slotsQ.error} />

      <Group align="flex-end">
        <Select
          label="Segment"
          placeholder="All segments"
          data={segmentOptions}
          value={segmentFilter}
          onChange={setSegmentFilter}
          clearable
          disabled={segments.length === 0}
        />
      </Group>

      <Card withBorder padding={0} radius="md">
        <Table.ScrollContainer minWidth={700}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                {SLOT_COLUMNS.map((column) => (
                  <SortableTableHeader
                    key={column.key}
                    label={column.label}
                    active={sort.key === column.key}
                    direction={sort.direction}
                    onSort={() => setSortKey(column.key)}
                  />
                ))}
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {visibleSlots.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={7}>
                    <Text c="dimmed" size="sm" ta="center" py="lg">
                      {slots.length === 0
                        ? "No slots configured."
                        : "No slots match the current filters."}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {visibleSlots.map((slot) => (
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
        segments={segmentOptions}
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
