import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/AppLayout";
import { Dashboard } from "@/pages/Dashboard";
import { Devices } from "@/pages/Devices";
import { DeviceDetail } from "@/pages/DeviceDetail";
import { BrokerConfig } from "@/pages/BrokerConfig";
import { LedStates } from "@/pages/LedStates";
import { Presets } from "@/pages/Presets";
import { ManualTest } from "@/pages/ManualTest";
import { Events } from "@/pages/Events";
import { Button, Center, Loader, Stack } from "@mantine/core";
import { useAuth } from "@/auth/AuthContext";
import { Login } from "@/pages/Login";
import { Users } from "@/pages/Users";
import { Account } from "@/pages/Account";
import { ErrorAlert } from "@/components/ErrorAlert";

export function App() {
  const { user, loading, error, retry } = useAuth();
  if (loading) return <Center mih="100vh"><Loader /></Center>;
  if (error) return <Center mih="100vh"><Stack>
    <ErrorAlert error={error} /><Button onClick={retry}>Retry connection</Button>
  </Stack></Center>;
  if (!user) return <Login />;
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/devices/:deviceId" element={<DeviceDetail />} />
        <Route path="/broker" element={<BrokerConfig />} />
        <Route path="/led-states" element={<LedStates />} />
        <Route path="/presets" element={<Presets />} />
        <Route path="/manual-test" element={user.role === "admin" ? <ManualTest /> : <Navigate to="/dashboard" replace />} />
        <Route path="/events" element={<Events />} />
        <Route path="/account" element={<Account />} />
        <Route path="/users" element={user.role === "admin" ? <Users /> : <Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
