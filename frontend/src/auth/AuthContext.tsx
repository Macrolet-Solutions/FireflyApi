import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import {
  checkAuth, getAuthUser, isApiError, refreshAuth, subscribeAuth,
} from "@/api/client";
import type { User } from "@/api/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  error: unknown;
  retry: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = useState(getAuthUser);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const previousUser = useRef(user);

  useEffect(() => subscribeAuth((next) => {
    const previous = previousUser.current;
    if (previous?.id !== next?.id || previous?.role !== next?.role || next === null) {
      void qc.cancelQueries();
      qc.clear();
    }
    previousUser.current = next;
    setUser(next);
  }), [qc]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    refreshAuth().catch((e: unknown) => {
      if (active && !(isApiError(e) && e.status === 401)) setError(e);
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [attempt]);

  useEffect(() => {
    if (!user) return;
    const verify = () => {
      checkAuth().catch((e: unknown) => {
        if (!(isApiError(e) && e.status === 401)) {
          notifications.show({
            color: "red", title: "Session check failed",
            message: e instanceof Error ? e.message : String(e),
          });
        }
      });
    };
    const timer = window.setInterval(verify, 60_000);
    window.addEventListener("focus", verify);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", verify);
    };
  }, [user?.id]);

  return (
    <AuthContext.Provider value={{ user, loading, error, retry: () => setAttempt((v) => v + 1) }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider.");
  return value;
}

export function AdminOnly({ children }: { children: ReactNode }) {
  return useAuth().user?.role === "admin" ? <>{children}</> : null;
}
