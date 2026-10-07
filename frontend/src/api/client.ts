// Tiny fetch wrapper. Backend errors come back as a structured envelope:
//   { errorCode, errorDescription, details }
// We throw ApiError so callers can branch on .errorCode.
import type { TokenResponse, User } from "@/api/types";

const AUTH = "/api/v1/auth";
let session: TokenResponse | null = null;
let expiresAt = 0;
let generation = 0;
let refreshPromise: Promise<TokenResponse> | null = null;
const listeners = new Set<(user: User | null) => void>();

export function getAuthUser(): User | null {
  return session?.user ?? null;
}

export function invalidateAuth() {
  generation += 1;
  setSession(null);
}

export function subscribeAuth(listener: (user: User | null) => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function setSession(value: TokenResponse | null) {
  session = value;
  expiresAt = value ? Date.now() + value.expiresIn * 1000 : 0;
  listeners.forEach((listener) => listener(value?.user ?? null));
}

export async function refreshAuth(): Promise<TokenResponse> {
  if (!refreshPromise) {
    const startedGeneration = generation;
    const refresh = async () => {
      // Serialize cookie rotation across tabs where Web Locks are available.
      const value = await rawRequest<TokenResponse>("POST", `${AUTH}/refresh`);
      if (generation !== startedGeneration) {
        throw new Error("Authentication operation was superseded.");
      }
      setSession(value);
      return value;
    };
    const withLock = async (): Promise<TokenResponse> => navigator.locks
      ? await navigator.locks.request("firefly-refresh", refresh)
      : await refresh();
    refreshPromise = withLock().catch((error: unknown) => {
      if (generation === startedGeneration && isApiError(error) && error.status === 401) {
        setSession(null);
      }
      throw error;
    }).finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

export async function loginAuth(username: string, password: string) {
  await waitForRefresh();
  const value = await rawRequest<TokenResponse>("POST", `${AUTH}/login`, { username, password });
  generation += 1;
  setSession(value);
}

export async function logoutAuth() {
  await waitForRefresh();
  await rawRequest<void>("POST", `${AUTH}/logout`);
  invalidateAuth();
}

async function waitForRefresh() {
  if (!refreshPromise) return;
  try {
    await refreshPromise;
  } catch (e) {
    if (!isApiError(e) || e.status !== 401) throw e;
  }
}

export async function changeAuthPassword(currentPassword: string, newPassword: string) {
  await request<void>("POST", `${AUTH}/password`, {
    current_password: currentPassword, new_password: newPassword,
  });
  invalidateAuth();
}

export async function checkAuth() {
  const user = await request<User>("GET", `${AUTH}/me`);
  if (session) {
    session = { ...session, user };
    listeners.forEach((listener) => listener(user));
  }
}

export interface ApiErrorBody {
  errorCode: string;
  errorDescription: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly errorCode: string;
  public readonly description: string;
  public readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.errorDescription || `HTTP ${status}`);
    this.status = status;
    this.errorCode = body.errorCode || "error";
    this.description = body.errorDescription || "";
    this.details = body.details || {};
  }
}

async function rawRequest<T>(
  method: string,
  path: string,
  body?: unknown,
  token?: string,
  acceptedStatuses: number[] = [],
): Promise<T> {
  const init: RequestInit = {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Firefly-CSRF": "1",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }
  const res = await fetch(path, init);
  if (res.status === 204) {
    return undefined as T;
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok && !acceptedStatuses.includes(res.status)) {
    throw new ApiError(res.status, data ?? {
      errorCode: "error",
      errorDescription: `HTTP ${res.status}`,
    });
  }
  return data as T;
}

async function request<T>(
  method: string, path: string, body?: unknown, acceptedStatuses: number[] = [],
): Promise<T> {
  const protectedRequest = path.startsWith("/api/v1/admin") || path.startsWith(AUTH);
  if (!protectedRequest) return rawRequest<T>(method, path, body);
  if (!session || Date.now() >= expiresAt - 30_000) await refreshAuth();
  if (path.startsWith("/api/v1/admin") && method !== "GET" && session?.user.role !== "admin") {
    throw new ApiError(403, {
      errorCode: "forbidden", errorDescription: "Administrator access required.",
    });
  }
  const usedToken = session?.accessToken;
  try {
    return await rawRequest<T>(method, path, body, usedToken, acceptedStatuses);
  } catch (error) {
    if (!isApiError(error) || error.status !== 401) throw error;
    if (session?.accessToken === usedToken) await refreshAuth();
    return rawRequest<T>(method, path, body, session?.accessToken, acceptedStatuses);
  }
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown, acceptedStatuses: number[] = []) =>
    request<T>("POST", path, body, acceptedStatuses),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}
