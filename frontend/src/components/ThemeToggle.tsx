import { ActionIcon, Tooltip, useMantineColorScheme } from "@mantine/core";
import { IconMoon, IconSun } from "@tabler/icons-react";

export function ThemeToggle() {
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const dark = colorScheme === "dark";
  return (
    <Tooltip label={dark ? "Switch to light mode" : "Switch to dark mode"}>
      <ActionIcon
        variant="default"
        size="lg"
        radius="md"
        onClick={() => toggleColorScheme()}
        aria-label="Toggle color scheme"
      >
        {dark ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}
