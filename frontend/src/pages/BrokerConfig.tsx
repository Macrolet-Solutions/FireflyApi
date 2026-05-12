import {
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Loader,
  NumberInput,
  PasswordInput,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import {
  IconCheck,
  IconInfoCircle,
  IconPlugConnected,
  IconRefresh,
  IconTrash,
  IconX,
} from "@tabler/icons-react";
import { useEffect, useMemo, useState } from "react";
import { isApiError } from "@/api/client";
import {
  useBrokers,
  useCreateBroker,
  useDeleteBroker,
  useTestBrokerConnection,
  useUpdateBroker,
} from "@/api/hooks";
import { ErrorAlert } from "@/components/ErrorAlert";
import { PageHeader } from "@/components/PageHeader";

interface BrokerFormValues {
  name: string;
  host: string;
  port: number | "";
  username: string;
  password: string;
  use_tls: boolean;
  client_id: string;
}

const EMPTY: BrokerFormValues = {
  name: "default",
  host: "localhost",
  port: 1883,
  username: "",
  password: "",
  use_tls: false,
  client_id: "firefly-api",
};

export function BrokerConfig() {
  const brokersQ = useBrokers();
  const create = useCreateBroker();
  const update = useUpdateBroker();
  const del = useDeleteBroker();
  const test = useTestBrokerConnection();

  const existing = brokersQ.data?.[0];
  const [editing, setEditing] = useState(false);

  const form = useForm<BrokerFormValues>({
    initialValues: EMPTY,
    validate: {
      name: (v) => (v.trim() ? null : "Required"),
      host: (v) => (v.trim() ? null : "Required"),
      port: (v) =>
        typeof v === "number" && v >= 1 && v <= 65535 ? null : "1-65535",
    },
  });

  useEffect(() => {
    if (existing) {
      form.setValues({
        name: existing.name,
        host: existing.host,
        port: existing.port,
        username: existing.username ?? "",
        password: "",
        use_tls: existing.use_tls,
        client_id: existing.client_id ?? "",
      });
    } else {
      form.setValues(EMPTY);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existing?.id]);

  const testResultBadge = useMemo(() => {
    if (!test.data) return null;
    if (test.data.success) {
      return (
        <Badge color="teal" variant="light" leftSection={<IconCheck size={12} />}>
          OK at {test.data.connectedAt}
        </Badge>
      );
    }
    return (
      <Badge color="red" variant="light" leftSection={<IconX size={12} />}>
        {test.data.errorCode}: {test.data.errorDescription}
      </Badge>
    );
  }, [test.data]);

  if (brokersQ.isLoading) return <Loader />;

  const handleSubmit = form.onSubmit(async (vals) => {
    const body = {
      name: vals.name.trim(),
      host: vals.host.trim(),
      port: Number(vals.port),
      username: vals.username.trim() || null,
      password: vals.password ? vals.password : null,
      use_tls: vals.use_tls,
      client_id: vals.client_id.trim() || null,
    };
    try {
      if (existing) {
        await update.mutateAsync({ id: existing.id, body });
        notifications.show({
          color: "teal",
          title: "Broker updated",
          message: "Restart the backend to apply broker changes.",
        });
      } else {
        await create.mutateAsync(body);
        notifications.show({
          color: "teal",
          title: "Broker created",
          message: "Restart the backend to start the actor runtime.",
        });
      }
      setEditing(false);
    } catch (e) {
      notifications.show({
        color: "red",
        title: "Could not save broker",
        message: isApiError(e) ? e.description : String(e),
      });
    }
  });

  const handleDelete = async () => {
    if (!existing) return;
    if (
      !confirm(
        `Delete broker "${existing.name}"? This will fail if any devices reference it.`,
      )
    ) {
      return;
    }
    try {
      await del.mutateAsync(existing.id);
      notifications.show({
        color: "teal",
        title: "Broker deleted",
        message: existing.name,
      });
    } catch (e) {
      notifications.show({
        color: "red",
        title: "Could not delete broker",
        message: isApiError(e) ? e.description : String(e),
      });
    }
  };

  return (
    <Stack>
      <PageHeader
        title="MQTT broker"
        description="Single broker connection used by every device actor (§7.1)."
      />

      <Alert
        icon={<IconInfoCircle size={16} />}
        color="firefly"
        variant="light"
        title="Broker config is loaded at backend startup"
      >
        <Text size="sm">
          Creating or updating the broker does not take effect until the
          backend is restarted (§11). Use{" "}
          <Code>python -m firefly_api --config …</Code> to relaunch after
          edits.
        </Text>
      </Alert>

      <ErrorAlert error={brokersQ.error} />

      <Card withBorder radius="md" padding="lg">
        {existing && !editing ? (
          <Stack>
            <Group justify="space-between">
              <Group>
                <Title order={4}>{existing.name}</Title>
                <Badge variant="light" color="firefly">
                  #{existing.id}
                </Badge>
              </Group>
              <Group>
                <Button
                  variant="default"
                  leftSection={<IconRefresh size={16} />}
                  onClick={() => setEditing(true)}
                >
                  Edit
                </Button>
                <Button
                  leftSection={<IconPlugConnected size={16} />}
                  loading={test.isPending}
                  onClick={() => test.mutate(existing.id)}
                >
                  Test connection
                </Button>
                <Button
                  variant="subtle"
                  color="red"
                  leftSection={<IconTrash size={16} />}
                  onClick={handleDelete}
                  loading={del.isPending}
                >
                  Delete
                </Button>
              </Group>
            </Group>

            <Stack gap={4}>
              <DetailRow label="Host" value={existing.host} />
              <DetailRow label="Port" value={String(existing.port)} />
              <DetailRow
                label="Username"
                value={existing.username || "(none)"}
              />
              <DetailRow
                label="Password"
                value={
                  <Text size="sm" c="dimmed">
                    (stored, redacted)
                  </Text>
                }
              />
              <DetailRow
                label="TLS"
                value={
                  existing.use_tls ? (
                    <Badge color="teal" variant="light">
                      enabled
                    </Badge>
                  ) : (
                    <Badge color="gray" variant="light">
                      off
                    </Badge>
                  )
                }
              />
              <DetailRow
                label="Client ID"
                value={existing.client_id || "(auto)"}
              />
            </Stack>

            {testResultBadge && <Group mt="md">{testResultBadge}</Group>}
          </Stack>
        ) : (
          <form onSubmit={handleSubmit}>
            <Stack>
              <Title order={4}>
                {existing ? "Edit broker" : "Create broker"}
              </Title>
              <Group grow>
                <TextInput
                  label="Name"
                  required
                  {...form.getInputProps("name")}
                />
                <TextInput
                  label="Host"
                  required
                  {...form.getInputProps("host")}
                />
                <NumberInput
                  label="Port"
                  min={1}
                  max={65535}
                  {...form.getInputProps("port")}
                />
              </Group>
              <Group grow>
                <TextInput
                  label="Username"
                  {...form.getInputProps("username")}
                />
                <PasswordInput
                  label="Password"
                  description={
                    existing
                      ? "Leave blank to keep the stored password."
                      : "Plain text (§12)."
                  }
                  {...form.getInputProps("password")}
                />
                <TextInput
                  label="Client ID"
                  description="Optional; defaults to the broker's auto-id."
                  {...form.getInputProps("client_id")}
                />
              </Group>
              <Switch
                label="Use TLS"
                {...form.getInputProps("use_tls", { type: "checkbox" })}
              />
              <Group justify="flex-end">
                {existing && (
                  <Button variant="default" onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                )}
                <Button type="submit" loading={create.isPending || update.isPending}>
                  {existing ? "Save changes" : "Create broker"}
                </Button>
              </Group>
            </Stack>
          </form>
        )}
      </Card>
    </Stack>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Group justify="space-between" py={4}>
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="sm" fw={500}>
        {value}
      </Text>
    </Group>
  );
}
