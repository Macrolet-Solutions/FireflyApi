import { Button, Card, PasswordInput, Stack, Text } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useState } from "react";
import { changeAuthPassword } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { ErrorAlert } from "@/components/ErrorAlert";
import { PageHeader } from "@/components/PageHeader";

export function Account() {
  const { user } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const form = useForm({
    initialValues: { current: "", password: "", confirm: "" },
    validate: {
      password: (v) => v.length >= 8 && v.length <= 128 ? null : "Use 8-128 characters.",
      confirm: (v, values) => v === values.password ? null : "Passwords do not match.",
    },
  });
  return (
    <Stack>
      <PageHeader title="My account" description={`${user?.username} (${user?.role})`} />
      <Card withBorder maw={480}>
        <form onSubmit={form.onSubmit(async (values) => {
          setPending(true);
          setError(null);
          try {
            await changeAuthPassword(values.current, values.password);
          } catch (e) {
            setError(e);
          } finally {
            setPending(false);
          }
        })}>
          <Stack>
            <Text size="sm">Changing your password signs you out on all devices.</Text>
            <ErrorAlert error={error} />
            <PasswordInput label="Current password" required autoComplete="current-password"
              {...form.getInputProps("current")} />
            <PasswordInput label="New password" required autoComplete="new-password"
              {...form.getInputProps("password")} />
            <PasswordInput label="Confirm new password" required autoComplete="new-password"
              {...form.getInputProps("confirm")} />
            <Button type="submit" loading={pending}>Change password</Button>
          </Stack>
        </form>
      </Card>
    </Stack>
  );
}
