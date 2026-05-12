import {
  Card,
  Grid,
  Group,
  Loader,
  RingProgress,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
  rem,
} from "@mantine/core";
import {
  IconActivity,
  IconAlertOctagon,
  IconAntenna,
  IconCircleCheck,
  IconCircleX,
  IconHelpHexagon,
} from "@tabler/icons-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useBrokers, useDevices, useEvents } from "@/api/hooks";
import { useDeviceStatusesByName } from "@/lib/deviceStatus";
import { ErrorAlert } from "@/components/ErrorAlert";
import { PageHeader } from "@/components/PageHeader";
import { StatusDot } from "@/components/StatusDot";
import { fmtAbs, fmtRel } from "@/lib/format";

interface CountTileProps {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  color: string;
}

function CountTile({ label, value, icon, color }: CountTileProps) {
  return (
    <Card withBorder radius="md" padding="md" className="hover-lift">
      <Group gap="md" wrap="nowrap">
        <ThemeIcon variant="light" color={color} size={44} radius="md">
          {icon}
        </ThemeIcon>
        <Stack gap={0}>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
            {label}
          </Text>
          <Title order={3}>{value}</Title>
        </Stack>
      </Group>
    </Card>
  );
}

export function Dashboard() {
  const devicesQ = useDevices();
  const brokersQ = useBrokers();
  const eventsQ = useEvents({ limit: 20 });

  const devices = devicesQ.data ?? [];
  const statuses = useDeviceStatusesByName(devices.map((d) => d.name));

  const counts = useMemo(() => {
    const c = { online: 0, offline: 0, register_error: 0, unknown: 0 };
    for (const device of devices) {
      const s = statuses[device.name];
      if (s) c[s.status] += 1;
    }
    return c;
  }, [devices, statuses]);

  const total = devices.length || 1;
  const onlinePct = (counts.online / total) * 100;
  const recentErrors = (eventsQ.data ?? []).filter(
    (e) => e.eventType === "error_received" || e.eventType === "timeout",
  );

  return (
    <Stack>
      <PageHeader
        title="Dashboard"
        description="Live overview of broker connectivity, device status, and recent device errors."
      />

      <ErrorAlert error={devicesQ.error || brokersQ.error || eventsQ.error} />

      <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="md">
        <CountTile
          label="Online"
          value={counts.online}
          icon={<IconCircleCheck size={22} />}
          color="teal"
        />
        <CountTile
          label="Offline"
          value={counts.offline}
          icon={<IconCircleX size={22} />}
          color="red"
        />
        <CountTile
          label="Register error"
          value={counts.register_error}
          icon={<IconAlertOctagon size={22} />}
          color="orange"
        />
        <CountTile
          label="Unknown"
          value={counts.unknown}
          icon={<IconHelpHexagon size={22} />}
          color="gray"
        />
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card withBorder radius="md" padding="lg" h="100%">
            <Stack align="center" gap="xs">
              <Text size="sm" c="dimmed" tt="uppercase" fw={600}>
                Fleet health
              </Text>
              <RingProgress
                size={160}
                thickness={14}
                roundCaps
                label={
                  <Stack gap={0} align="center">
                    <Title order={2}>{Math.round(onlinePct)}%</Title>
                    <Text size="xs" c="dimmed">
                      online
                    </Text>
                  </Stack>
                }
                sections={[
                  { value: (counts.online / total) * 100, color: "teal" },
                  { value: (counts.offline / total) * 100, color: "red" },
                  {
                    value: (counts.register_error / total) * 100,
                    color: "orange",
                  },
                  { value: (counts.unknown / total) * 100, color: "gray" },
                ]}
              />
              <Text size="xs" c="dimmed">
                {devices.length} configured device
                {devices.length === 1 ? "" : "s"}
              </Text>
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 8 }}>
          <Card withBorder radius="md" padding="lg" h="100%">
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <ThemeIcon
                  variant="light"
                  color="firefly"
                  size={28}
                  radius="md"
                >
                  <IconAntenna size={16} />
                </ThemeIcon>
                <Title order={5}>Devices</Title>
              </Group>
              <Link
                to="/devices"
                style={{ fontSize: rem(13), textDecoration: "none" }}
              >
                Manage &rsaquo;
              </Link>
            </Group>
            {devicesQ.isLoading ? (
              <Loader />
            ) : devices.length === 0 ? (
              <Text c="dimmed" size="sm">
                No devices configured yet.
              </Text>
            ) : (
              <ScrollArea h={280}>
                <Table verticalSpacing="xs">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Name</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Firmware</Table.Th>
                      <Table.Th>Last keepalive</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {devices.map((d) => {
                      const s = statuses[d.name];
                      return (
                        <Table.Tr key={d.id}>
                          <Table.Td>
                            <Link
                              to={`/devices/${d.id}`}
                              style={{ color: "inherit" }}
                            >
                              <Text fw={500}>{d.display_name || d.name}</Text>
                              {d.display_name && (
                                <Text size="xs" c="dimmed">
                                  {d.name}
                                </Text>
                              )}
                            </Link>
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
                            <Text size="sm" c="dimmed">
                              {fmtRel(s?.lastKeepaliveAt)}
                            </Text>
                          </Table.Td>
                        </Table.Tr>
                      );
                    })}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            )}
          </Card>
        </Grid.Col>

        <Grid.Col span={12}>
          <Card withBorder radius="md" padding="lg">
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <ThemeIcon variant="light" color="red" size={28} radius="md">
                  <IconActivity size={16} />
                </ThemeIcon>
                <Title order={5}>Recent errors &amp; timeouts</Title>
              </Group>
              <Link
                to="/events"
                style={{ fontSize: rem(13), textDecoration: "none" }}
              >
                See all events &rsaquo;
              </Link>
            </Group>
            {recentErrors.length === 0 ? (
              <Text c="dimmed" size="sm">
                No recent errors. 🎉
              </Text>
            ) : (
              <Table verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>When</Table.Th>
                    <Table.Th>Type</Table.Th>
                    <Table.Th>Code</Table.Th>
                    <Table.Th>Description</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {recentErrors.slice(0, 8).map((e) => (
                    <Table.Tr key={e.id}>
                      <Table.Td>
                        <Text size="xs" c="dimmed">
                          {fmtAbs(e.createdAt)}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{e.eventType}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" ff="monospace">
                          {e.errorCode || "—"}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{e.errorDescription || "—"}</Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
