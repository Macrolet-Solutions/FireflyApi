// Tiny fetch wrapper. Backend errors come back as a structured envelope:
//   { errorCode, errorDescription, details }
// We throw ApiError so callers can branch on .errorCode.

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

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const init: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
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
  if (!res.ok) {
    throw new ApiError(res.status, data ?? {
      errorCode: "error",
      errorDescription: `HTTP ${res.status}`,
    });
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}
