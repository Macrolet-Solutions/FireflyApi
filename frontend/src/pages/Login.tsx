import { Button, Group, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import {
  IconActivity,
  IconArrowRight,
  IconCpu,
  IconLock,
  IconSettings,
  IconShieldCheck,
  IconUser,
} from "@tabler/icons-react";
import { useState } from "react";
import { loginAuth } from "@/api/client";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ThemeToggle } from "@/components/ThemeToggle";
import classes from "./Login.module.css";

const FEATURES = [
  { icon: IconCpu, label: "Monitor your controllers" },
  { icon: IconSettings, label: "Manage device configuration" },
  { icon: IconActivity, label: "Keep operations in sight" },
];

export function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return (
    <main className={classes.page}>
      <header className={classes.pageHeader}>
        <Text className={classes.consoleLabel}>FIREFLY MANAGEMENT CONSOLE</Text>
        <ThemeToggle />
      </header>

      <section className={classes.shell} aria-label="Firefly sign in">
        <div className={classes.brandPanel}>
          <div className={classes.brandContent}>
            <img
              src="/logo-firefly.png"
              alt="Firefly"
              className={classes.logo}
            />
            <div className={classes.brandIntro}>
              <Text className={classes.eyebrow}>CONNECTED. CONFIGURED. IN CONTROL.</Text>
              <Title order={2} className={classes.brandTitle}>
                Bring your operations<br />to light.
              </Title>
              <Text className={classes.brandDescription}>
                One workspace to configure, monitor, and maintain your Firefly devices.
              </Text>
            </div>
            <Stack gap="md" className={classes.features}>
              {FEATURES.map(({ icon: Icon, label }) => (
                <Group key={label} gap="sm" wrap="nowrap">
                  <span className={classes.featureIcon}><Icon size={18} stroke={1.6} /></span>
                  <Text size="sm">{label}</Text>
                </Group>
              ))}
            </Stack>
          </div>
          <div className={classes.lightGrid} aria-hidden="true">
            {[0, 1, 2].map((row) => (
              <div className={classes.lightTrack} key={row}>
                {[0, 1, 2, 3, 4, 5, 6].map((led) => <span key={led} />)}
              </div>
            ))}
          </div>
          <Text className={classes.brandFooter}>Built for brighter operations.</Text>
        </div>

        <div className={classes.formPanel}>
          <div className={classes.formContent}>
            <div className={classes.welcomeIcon} aria-hidden="true">
              <IconLock size={24} stroke={1.5} />
            </div>
            <Title order={1} className={classes.formTitle}>Welcome back</Title>
            <Text className={classes.formDescription}>
              Sign in to your Firefly workspace.
            </Text>
            <form onSubmit={async (event) => {
              event.preventDefault();
              if (pending) return;
              setPending(true);
              setError(null);
              try {
                await loginAuth(username, password);
              } catch (e) {
                setError(e);
              } finally {
                setPending(false);
              }
            }}>
              <Stack gap="lg">
                <div className={classes.error} aria-live="polite"><ErrorAlert error={error} /></div>
                <TextInput
                  label="Username"
                  placeholder="Enter your username"
                  required
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  size="md"
                  leftSection={<IconUser size={18} stroke={1.5} />}
                  classNames={{ input: classes.input, label: classes.inputLabel }}
                  value={username}
                  onChange={(e) => setUsername(e.currentTarget.value)}
                />
                <PasswordInput
                  label="Password"
                  placeholder="Enter your password"
                  required
                  autoComplete="current-password"
                  size="md"
                  leftSection={<IconLock size={18} stroke={1.5} />}
                  classNames={{ input: classes.input, label: classes.inputLabel }}
                  value={password}
                  onChange={(e) => setPassword(e.currentTarget.value)}
                />
                <Button
                  type="submit"
                  loading={pending}
                  fullWidth
                  size="md"
                  rightSection={<IconArrowRight size={18} />}
                  className={classes.signIn}
                >
                  Sign in
                </Button>
              </Stack>
            </form>
            <Text className={classes.accountHelp}>
              Need an account? Contact your administrator.
            </Text>
            <div className={classes.accessNote}>
              <IconShieldCheck size={18} stroke={1.5} aria-hidden="true" />
              <Text size="xs">Access is managed by your organization.</Text>
            </div>
          </div>
        </div>
      </section>

      <footer className={classes.pageFooter}>
        <Text size="xs">Macrolet Solutions</Text>
        <Text size="xs">Firefly API Service</Text>
      </footer>
    </main>
  );
}
