import {
  ActionIcon,
  Anchor,
  Button,
  Card,
  Group,
  Modal,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
  Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import {
  IconExternalLink,
  IconPlus,
  IconTrash,
} from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { isApiError } from "@/api/client";
import {
  useBrokers,
  useCreateDevice,
  useDeleteDevice,
  useDevices,
} from "@/api/hooks";
import { useDeviceStatusesByName } from "@/lib/deviceStatus";
import { ErrorAlert } from "@/components/ErrorAlert";
import { PageHeader } from "@/components/PageHeader";
import { StatusDot } from "@/components/StatusDot";
import { fmtRel } from "@/lib/format";

export function Devices() {
  const devicesQ = useDevices();
  const brokersQ = useBrokers();
  const createDevice = useCreateDevice();
  const deleteDevice = useDeleteDevice();
  const [addOpen, setAddOpen] = useState(false);
  const devices = devicesQ.data ?? [];
  const brokers = brokersQ.data ?? [];
  const statuses = useDeviceStatusesByName(devices.map((d) => d.name));

  const form = useForm({
    initialValues: {
      name: "",
      display_name: "",
      description: "",
      mqtt_broker_id: brokers[0]?.id ? String(brokers[0].id) : "",
    },
    validate: {
      name: (v) => (v.trim() ? null : "Required"),
      mqtt_broker_id: (v) => (v ? null : "Required"),
    },
  });

  const handleSubmit = form.onSubmit(async (values) => {
    try {
      await createDevice.mutateAsync({
        name: values.name.trim(),
        display_name: values.display_name.trim() || null,
        description: values.description.trim() || null,
        mqtt_broker_id: Number(values.mqtt_broker_id),
      });
      notifications.show({
        color: "teal",
        title: "Device created",
        message: `${values.name} is now configured.`,
      });
      form.reset();
      setAddOpen(false);
    } catch (e) {
      notifications.show({
        color: "red",
        title: "Could not create device",
        message: isApiError(e) ? e.description : String(e),
      });
    }
  });

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Delete device "${name}" and all of its segments and slots?`)) {
      return;
    }
    try {
      await deleteDevice.mutateAsync(id);
      notifications.show({
        color: "teal",
        title: "Device deleted",
        message: name,
      });
    } catch (e) {
      notifications.show({
        color: "red",
        title: "Could not delete device",
        message: isApiError(e) ? e.description : String(e),
      });
    }
  };

  return (
    <Stack>
      <PageHeader
        title="Devices"
        description="Physical Firefly controllers known to this service."
        right={
          <Button
            leftSection={<IconPlus size={16} />}
            disabled={brokers.length === 0}
            onClick={() => setAddOpen(true)}
          >
            Add device
          </Button>
        }
      />

      {brokers.length === 0 && (
        <Card withBorder radius="md" mb="md">
          <Group justify="space-between">
            <div>
              <Title order={5}>No MQTT broker configured</Title>
              <Text size="sm" c="dimmed">
                Create a broker before adding devices. Backend restart is
                required after creating one.
              </Text>
            </div>
            <Button component={Link} to="/broker">
              Configure broker
            </Button>
          </Group>
        </Card>
      )}

      <ErrorAlert error={devicesQ.error || brokersQ.error} />

      <Card withBorder radius="md" padding={0}>
        <Table.ScrollContainer minWidth={800}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Device</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Firmware</Table.Th>
                <Table.Th>MAC</Table.Th>
                <Table.Th>Last keepalive</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {devices.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={6}>
                    <Text c="dimmed" size="sm" ta="center" py="lg">
                      No devices yet. Add one with the button above.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {devices.map((d) => {
                const s = statuses[d.name];
                return (
                  <Table.Tr key={d.id}>
                    <Table.Td>
                      <Anchor
                        component={Link}
                        to={`/devices/${d.id}`}
                        fw={500}
                      >
                        {d.display_name || d.name}
                      </Anchor>
                      {d.display_name && (
                        <Text size="xs" c="dimmed">
                          {d.name}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {s ? (
                        <StatusDot status={s.status} />
                      ) : (
                        <Text size="sm" c="dimmed">
                          —
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{s?.firmwareVersion || "—"}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace">
                        {s?.macAddress || "—"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {fmtRel(s?.lastKeepaliveAt)}
                      </Text>
                    </Table.Td>
                    <Table.Td style={{ textAlign: "right" }}>
                      <Group gap="xs" justify="flex-end">
                        <Tooltip label="Open">
                          <ActionIcon
                            component={Link}
                            to={`/devices/${d.id}`}
                            variant="subtle"
                          >
                            <IconExternalLink size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip label="Delete">
                          <ActionIcon
                            color="red"
                            variant="subtle"
                            onClick={() => handleDelete(d.id, d.name)}
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

      <Modal
        opened={addOpen}
        onClose={() => setAddOpen(false)}
        title="Add device"
        centered
      >
        <form onSubmit={handleSubmit}>
          <Stack>
            <TextInput
              label="Device name"
              placeholder="FF01"
              description="The MQTT identifier reported by the firmware."
              required
              {...form.getInputProps("name")}
            />
            <TextInput
              label="Display name"
              placeholder="Aisle 1 — north"
              {...form.getInputProps("display_name")}
            />
            <Textarea
              label="Description"
              placeholder="Optional"
              autosize
              minRows={2}
              {...form.getInputProps("description")}
            />
            <Select
              label="MQTT broker"
              data={brokers.map((b) => ({
                value: String(b.id),
                label: b.name,
              }))}
              required
              {...form.getInputProps("mqtt_broker_id")}
            />
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setAddOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={createDevice.isPending}>
                Create
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
