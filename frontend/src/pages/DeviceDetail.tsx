import {
  ActionIcon,
  Badge,
  Button,
  Card,
  CopyButton,
  Divider,
  Group,
  Loader,
  Modal,
  Stack,
  Tabs,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconArrowBack,
  IconCheck,
  IconCopy,
  IconLayoutGrid,
  IconPlayerPlay,
  IconPlayerStop,
  IconRefresh,
  IconRouter,
  IconSettings,
} from "@tabler/icons-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { isApiError } from "@/api/client";
import {
  useDevice,
  useDeviceStatus,
  useReinitialize,
  useResetDevice,
  useStartActor,
  useStopActor,
} from "@/api/hooks";
import type { ActorLifecycleResponse } from "@/api/types";
import { ErrorAlert } from "@/components/ErrorAlert";
import { PageHeader } from "@/components/PageHeader";
import { StatusDot } from "@/components/StatusDot";
import { fmtAbs, fmtRel } from "@/lib/format";
import { SegmentsTab } from "@/pages/device/SegmentsTab";
import { SlotsTab } from "@/pages/device/SlotsTab";

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Group justify="space-between" wrap="nowrap" py={4}>
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="sm" fw={500} ff={typeof value === "string" ? "monospace" : undefined}>
        {value}
      </Text>
    </Group>
  );
}

export function DeviceDetail() {
  const params = useParams<{ deviceId: string }>();
  const navigate = useNavigate();
  const deviceId = params.deviceId ? Number(params.deviceId) : undefined;
  const deviceQ = useDevice(deviceId);
  const statusQ = useDeviceStatus(deviceQ.data?.name);

  const startActor = useStartActor();
  const stopActor = useStopActor();
  const reinit = useReinitialize();
  const resetDev = useResetDevice();

  const [resetOpen, setResetOpen] = useState(false);

  if (deviceQ.isLoading) return <Loader />;
  if (!deviceQ.data) return <ErrorAlert error={deviceQ.error} />;

  const device = deviceQ.data;
  const status = statusQ.data;

  const handleStart = () => doLifecycle(startActor.mutateAsync(device.id), "Actor started");
  const handleStop = () => doLifecycle(stopActor.mutateAsync(device.id), "Actor stopped");
  const handleReinit = () =>
    doAction(
      reinit.mutateAsync({ deviceId: device.id }),
      "Slots reinitialized",
    );
  const handleReset = async () => {
    setResetOpen(false);
    try {
      await resetDev.mutateAsync(device.id);
      notifications.show({
        color: "yellow",
        title: "Reset published",
        message:
          "The device will reboot and re-register. Status will return to online once init-slots is ACK'd.",
      });
    } catch (e) {
      notifications.show({
        color: "red",
        title: "Reset failed",
        message: isApiError(e) ? e.description : String(e),
      });
    }
  };

  return (
    <Stack>
      <PageHeader
        title={device.display_name || device.name}
        description={
          device.display_name ? `MQTT name: ${device.name}` : device.description ?? undefined
        }
        right={
          <Group>
            <Button
              variant="default"
              leftSection={<IconArrowBack size={16} />}
              onClick={() => navigate("/devices")}
            >
              Back
            </Button>
          </Group>
        }
      />

      <Card withBorder radius="md" padding="lg">
        <Group justify="space-between" align="flex-start" wrap="wrap">
          <Stack gap={4}>
            <Group gap="xs">
              <IconRouter size={20} />
              <Title order={4}>Live status</Title>
              {status && <StatusDot status={status.status} />}
            </Group>
            <Text size="xs" c="dimmed">
              Polled every 3 s. All runtime fields come from the in-memory actor.
            </Text>
          </Stack>

          <Group>
            <Tooltip label="Push a fresh init-slots to apply slot changes.">
              <Button
                variant="default"
                leftSection={<IconRefresh size={16} />}
                onClick={handleReinit}
                loading={reinit.isPending}
              >
                Reinitialize
              </Button>
            </Tooltip>
            <Tooltip label="Hard restart the device (required to apply segment or LED-state changes).">
              <Button
                color="yellow"
                variant="light"
                leftSection={<IconRefresh size={16} />}
                onClick={() => setResetOpen(true)}
              >
                Reset device
              </Button>
            </Tooltip>
            <Tooltip label="Stop the actor (transient — gone on backend restart).">
              <Button
                variant="default"
                color="red"
                leftSection={<IconPlayerStop size={16} />}
                onClick={handleStop}
                loading={stopActor.isPending}
              >
                Stop actor
              </Button>
            </Tooltip>
            <Tooltip label="Re-create the actor if it was stopped.">
              <Button
                variant="default"
                color="teal"
                leftSection={<IconPlayerPlay size={16} />}
                onClick={handleStart}
                loading={startActor.isPending}
              >
                Start actor
              </Button>
            </Tooltip>
          </Group>
        </Group>

        <Divider my="md" />

        <Group grow align="flex-start" wrap="wrap">
          <Stack gap={2} miw={260}>
            <MetaRow
              label="Firmware"
              value={status?.firmwareVersion || "—"}
            />
            <MetaRow label="MAC" value={status?.macAddress || "—"} />
            <MetaRow
              label="Registered at"
              value={fmtAbs(status?.registeredAt)}
            />
          </Stack>
          <Stack gap={2} miw={260}>
            <MetaRow
              label="Last keepalive"
              value={fmtRel(status?.lastKeepaliveAt)}
            />
            <MetaRow
              label="Current task ID"
              value={
                status?.currentTaskId ? (
                  <CopyButton value={status.currentTaskId}>
                    {({ copied, copy }) => (
                      <Group gap={4} wrap="nowrap">
                        <Text size="sm" ff="monospace">
                          {status.currentTaskId!.slice(0, 8)}…
                        </Text>
                        <ActionIcon
                          variant="subtle"
                          onClick={copy}
                          size="sm"
                          aria-label="Copy task ID"
                        >
                          {copied ? (
                            <IconCheck size={14} />
                          ) : (
                            <IconCopy size={14} />
                          )}
                        </ActionIcon>
                      </Group>
                    )}
                  </CopyButton>
                ) : (
                  "—"
                )
              }
            />
            <MetaRow
              label="MQTT broker"
              value={
                <Badge variant="light" color="firefly">
                  #{device.mqtt_broker_id}
                </Badge>
              }
            />
          </Stack>
        </Group>
      </Card>

      <Tabs defaultValue="segments" variant="default" radius="md" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="segments" leftSection={<IconLayoutGrid size={16} />}>
            Segments
          </Tabs.Tab>
          <Tabs.Tab value="slots" leftSection={<IconSettings size={16} />}>
            Slots
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="segments" pt="lg">
          <SegmentsTab deviceId={device.id} />
        </Tabs.Panel>
        <Tabs.Panel value="slots" pt="lg">
          <SlotsTab deviceId={device.id} />
        </Tabs.Panel>
      </Tabs>

      <Modal
        opened={resetOpen}
        onClose={() => setResetOpen(false)}
        title="Reset device?"
        centered
      >
        <Text size="sm" mb="md">
          The device will reboot and re-register with the latest LED state
          catalog and segment definitions. In-flight commands will be
          aborted. Continue?
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setResetOpen(false)}>
            Cancel
          </Button>
          <Button color="yellow" onClick={handleReset} loading={resetDev.isPending}>
            Reset device
          </Button>
        </Group>
      </Modal>
    </Stack>
  );
}

async function doLifecycle(
  promise: Promise<ActorLifecycleResponse>,
  successTitle: string,
) {
  try {
    const res = await promise;
    notifications.show({
      color: "teal",
      title: successTitle,
      message: res.actorStatus,
    });
  } catch (e) {
    notifications.show({
      color: "red",
      title: "Action failed",
      message: isApiError(e) ? e.description : String(e),
    });
  }
}

async function doAction<T>(promise: Promise<T>, successTitle: string) {
  try {
    await promise;
    notifications.show({
      color: "teal",
      title: successTitle,
      message: "Command ACK'd by device.",
    });
  } catch (e) {
    notifications.show({
      color: "red",
      title: "Action failed",
      message: isApiError(e) ? e.description : String(e),
    });
  }
}
