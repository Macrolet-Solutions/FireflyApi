import {
  ActionIcon, Badge, Button, Card, Group, Modal, PasswordInput, Select,
  Stack, Switch, Table, Text, TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, invalidateAuth, isApiError } from "@/api/client";
import type { User, UserInput } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { ErrorAlert } from "@/components/ErrorAlert";
import { PageHeader } from "@/components/PageHeader";
import { fmtAbs } from "@/lib/format";

const PATH = "/api/v1/admin/users";

export function Users() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>(PATH) });
  const [editing, setEditing] = useState<User | null>(null);
  const [opened, setOpened] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const form = useForm<{ username: string; password: string; role: User["role"]; enabled: boolean }>({
    initialValues: { username: "", password: "", role: "viewer", enabled: true },
    validate: {
      username: (v) => v.trim().length > 0 && v.trim().length <= 100 ? null : "Use 1-100 characters.",
      password: (v) => (editing && !v) || (v.length >= 8 && v.length <= 128)
        ? null : "Use 8-128 characters.",
    },
  });
  const save = useMutation({
    mutationFn: (body: UserInput) => editing
      ? api.put<User>(`${PATH}/${editing.id}`, body)
      : api.post<User>(PATH, body),
    onSuccess: async (saved, body) => {
      setOpened(false);
      await qc.invalidateQueries({ queryKey: ["users"] });
      if (saved.id === user?.id && (
        body.password || saved.username !== user.username ||
        saved.role !== user.role || saved.enabled !== user.enabled
      )) {
        notifications.show({ title: "Account updated", message: "Please sign in again." });
        invalidateAuth();
      }
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del<void>(`${PATH}/${id}`),
    onSuccess: async (_data, id) => {
      await qc.invalidateQueries({ queryKey: ["users"] });
      if (id === user?.id) invalidateAuth();
    },
  });

  function open(value: User | null) {
    setEditing(value);
    setError(null);
    form.setValues({
      username: value?.username ?? "", password: "",
      role: value?.role ?? "viewer", enabled: value?.enabled ?? true,
    });
    form.clearErrors();
    setOpened(true);
  }

  return (
    <Stack>
      <PageHeader title="Users" description="Manage admin and read-only viewer accounts."
        right={<Button leftSection={<IconPlus size={16} />} onClick={() => open(null)}>Add user</Button>} />
      <ErrorAlert error={q.error} />
      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={700}>
          <Table>
            <Table.Thead><Table.Tr>
              <Table.Th>Username</Table.Th><Table.Th>Role</Table.Th><Table.Th>Status</Table.Th>
              <Table.Th>Created</Table.Th><Table.Th>Last login</Table.Th><Table.Th>Actions</Table.Th>
            </Table.Tr></Table.Thead>
            <Table.Tbody>
              {(q.data ?? []).map((row) => (
                <Table.Tr key={row.id}>
                  <Table.Td>{row.username}</Table.Td>
                  <Table.Td><Badge>{row.role}</Badge></Table.Td>
                  <Table.Td>{row.enabled ? "Enabled" : "Disabled"}</Table.Td>
                  <Table.Td>{fmtAbs(row.created_at)}</Table.Td>
                  <Table.Td>{fmtAbs(row.last_login_at)}</Table.Td>
                  <Table.Td><Group gap="xs">
                    <ActionIcon variant="subtle" aria-label={`Edit ${row.username}`} onClick={() => open(row)}>
                      <IconPencil size={16} />
                    </ActionIcon>
                    <ActionIcon variant="subtle" color="red" aria-label={`Delete ${row.username}`}
                      loading={remove.isPending}
                      onClick={async () => {
                        if (!confirm(`Delete user "${row.username}"?`)) return;
                        try {
                          await remove.mutateAsync(row.id);
                        } catch (e) {
                          notifications.show({
                            color: "red", title: "Could not delete user",
                            message: isApiError(e) ? e.description : String(e),
                          });
                        }
                      }}>
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Modal opened={opened} onClose={() => setOpened(false)} title={editing ? "Edit user" : "Add user"}>
        <form onSubmit={form.onSubmit(async (values) => {
          setError(null);
          try {
            await save.mutateAsync({
              username: values.username, role: values.role, enabled: values.enabled,
              ...(values.password ? { password: values.password } : {}),
            });
          } catch (e) {
            setError(e);
          }
        })}>
          <Stack>
            <ErrorAlert error={error} />
            <TextInput label="Username" required autoComplete="off" {...form.getInputProps("username")} />
            <PasswordInput label={editing ? "New password (leave blank to keep)" : "Password"}
              required={!editing} autoComplete="new-password" {...form.getInputProps("password")} />
            <Select label="Role" data={["viewer", "admin"]} allowDeselect={false}
              value={form.values.role}
              onChange={(value) => { if (value === "viewer" || value === "admin") form.setFieldValue("role", value); }} />
            <Switch label="Account enabled" {...form.getInputProps("enabled", { type: "checkbox" })} />
            <Text size="xs" c="dimmed">Password, username, role, or status changes revoke existing sessions.</Text>
            <Button type="submit" loading={save.isPending}>Save</Button>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
