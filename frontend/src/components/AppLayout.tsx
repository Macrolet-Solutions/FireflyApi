import {
  AppShell,
  Button,
  Burger,
  Group,
  NavLink,
  ScrollArea,
  Text,
  Title,
  rem,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconActivity,
  IconCpu,
  IconDashboard,
  IconGauge,
  IconHistory,
  IconPalette,
  IconStack2,
} from "@tabler/icons-react";
import { NavLink as RouterNavLink, Outlet, useLocation } from "react-router-dom";
import { BrokerStatusBadge } from "@/components/BrokerStatusBadge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { IconUser, IconUsers } from "@tabler/icons-react";
import { useState } from "react";
import { useAuth } from "@/auth/AuthContext";
import { isApiError, logoutAuth } from "@/api/client";
import { notifications } from "@mantine/notifications";

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: <IconDashboard size={18} /> },
  { to: "/devices", label: "Devices", icon: <IconCpu size={18} /> },
  { to: "/led-states", label: "LED States", icon: <IconPalette size={18} /> },
  { to: "/presets", label: "Command Presets", icon: <IconStack2 size={18} /> },
  { to: "/manual-test", label: "Manual Test", icon: <IconGauge size={18} /> },
  { to: "/events", label: "Event Log", icon: <IconHistory size={18} /> },
  { to: "/broker", label: "MQTT Broker", icon: <IconActivity size={18} /> },
];

export function AppLayout() {
  const { user } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);
  const [opened, { toggle }] = useDisclosure();
  const location = useLocation();

  return (
    <AppShell
      header={{ height: 64 }}
      navbar={{
        width: 240,
        breakpoint: "sm",
        collapsed: { mobile: !opened },
      }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
            />
            <img
              src="/logo-firefly.png"
              alt="Firefly"
              className="brand-glow"
              style={{ height: 36, width: "auto" }}
            />
            <div>
              <Title order={4} fw={600} style={{ lineHeight: 1 }}>
                Firefly API
              </Title>
              <Text size="xs" c="dimmed" style={{ lineHeight: 1 }}>
                Macrolet device middleware
              </Text>
            </div>
          </Group>
          <Group gap="xs">
            <Text size="sm">{user?.username} ({user?.role})</Text>
            <Button variant="subtle" loading={loggingOut} onClick={async () => {
              setLoggingOut(true);
              try {
                await logoutAuth();
              } catch (e) {
                notifications.show({
                  color: "red", title: "Logout failed",
                  message: isApiError(e) ? e.description : String(e),
                });
              } finally {
                setLoggingOut(false);
              }
            }}>Logout</Button>
            <BrokerStatusBadge />
            <ThemeToggle />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        <AppShell.Section grow component={ScrollArea}>
          {[
            ...NAV_ITEMS.filter((item) => item.to !== "/manual-test" || user?.role === "admin"),
            { to: "/account", label: "My account", icon: <IconUser size={18} /> },
            ...(user?.role === "admin" ? [{ to: "/users", label: "Users", icon: <IconUsers size={18} /> }] : []),
          ].map((item) => (
            <NavLink
              key={item.to}
              component={RouterNavLink}
              to={item.to}
              label={item.label}
              leftSection={item.icon}
              active={
                location.pathname === item.to ||
                location.pathname.startsWith(`${item.to}/`)
              }
              variant="light"
              style={{ borderRadius: rem(8), marginBottom: rem(2) }}
            />
          ))}
        </AppShell.Section>
        <AppShell.Section>
          <Text size="xs" c="dimmed" ta="center" mt="md">
            v0.1.0 &middot; Firefly API
          </Text>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
