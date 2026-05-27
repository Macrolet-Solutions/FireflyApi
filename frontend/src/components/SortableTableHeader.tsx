import { ActionIcon, Group, Table, Text, Tooltip } from "@mantine/core";
import {
  IconArrowsSort,
  IconSortAscending,
  IconSortDescending,
} from "@tabler/icons-react";

export type SortDirection = "asc" | "desc";

interface Props {
  label: string;
  active: boolean;
  direction: SortDirection;
  onSort: () => void;
}

export function SortableTableHeader({
  label,
  active,
  direction,
  onSort,
}: Props) {
  const Icon = active
    ? direction === "asc"
      ? IconSortAscending
      : IconSortDescending
    : IconArrowsSort;
  const nextDirection = active && direction === "asc" ? "descending" : "ascending";

  return (
    <Table.Th>
      <Group gap="xs" wrap="nowrap">
        <Text component="span" size="sm" fw={600}>
          {label}
        </Text>
        <Tooltip label={`Sort ${nextDirection}`}>
          <ActionIcon
            aria-label={`Sort ${label} ${nextDirection}`}
            size="sm"
            variant={active ? "light" : "subtle"}
            onClick={onSort}
          >
            <Icon size={14} />
          </ActionIcon>
        </Tooltip>
      </Group>
    </Table.Th>
  );
}