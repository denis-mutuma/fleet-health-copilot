/**
 * Shared orchestrator API client utilities.
 * All lib modules use this to ensure consistent URL resolution and error handling.
 */

const DEFAULT_ORCHESTRATOR_URL = "http://127.0.0.1:8000";

type ErrorPayload = {
  detail: string;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
};

export class OrchestratorRequestError extends Error {
  constructor(
    readonly status: number,
    readonly payload: unknown
  ) {
    super(`Orchestrator request failed (${status})`);
  }
}

export function orchestratorBaseUrl(): string {
  const configuredUrl =
    process.env.ORCHESTRATOR_API_BASE_URL ??
    process.env.NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL ??
    DEFAULT_ORCHESTRATOR_URL;
  return configuredUrl.replace(/\/+$/, "");
}

export async function orchestratorRequest<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const headers = new Headers(init?.headers);
  const isFormDataBody = typeof FormData !== "undefined" && init?.body instanceof FormData;
  if (!headers.has("content-type") && !isFormDataBody) {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(`${orchestratorBaseUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers,
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new OrchestratorRequestError(response.status, payload);
  }

  return payload as T;
}

export function apiErrorPayload(
  message: string,
  code: string,
  details?: Record<string, unknown>
): ErrorPayload {
  return {
    detail: message,
    error: {
      code,
      message,
      ...(details ? { details } : {})
    }
  };
}

export function readApiErrorMessage(payload: unknown, fallback: string): string {
  if (typeof payload !== "object" || payload === null) {
    return fallback;
  }

  if ("detail" in payload && typeof (payload as { detail?: unknown }).detail === "string") {
    return (payload as { detail: string }).detail;
  }

  if (
    "error" in payload &&
    typeof (payload as { error?: unknown }).error === "object" &&
    (payload as { error: { message?: unknown } }).error !== null &&
    typeof (payload as { error: { message?: unknown } }).error.message === "string"
  ) {
    return (payload as { error: { message: string } }).error.message;
  }

  return fallback;
}

/** Serialize an OrchestratorRequestError into a user-facing { status, message } pair. */
export function toApiError(error: unknown): { status: number; message: string } {
  if (error instanceof OrchestratorRequestError) {
    const detail = readApiErrorMessage(error.payload, "Request failed.");
    return { status: error.status, message: detail };
  }
  return { status: 500, message: "Unexpected request failure." };
}
