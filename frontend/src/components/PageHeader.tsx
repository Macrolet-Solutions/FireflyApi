import { Box, Group, Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

interface Props {
  title: string;
  description?: string;
  right?: ReactNode;
}

export function PageHeader({ title, description, right }: Props) {
  return (
    <Group justify="space-between" align="flex-end" mb="lg">
      <Stack gap={4}>
        <Title order={2}>{title}</Title>
        {description && (
          <Text c="dimmed" size="sm">
            {description}
          </Text>
        )}
      </Stack>
      {right && <Box>{right}</Box>}
    </Group>
  );
}
