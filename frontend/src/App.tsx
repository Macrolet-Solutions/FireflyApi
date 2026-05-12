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

export function App() {
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
        <Route path="/manual-test" element={<ManualTest />} />
        <Route path="/events" element={<Events />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
