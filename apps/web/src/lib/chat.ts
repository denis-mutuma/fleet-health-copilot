export type ChatCitation = {
  document_id: string;
  source: string;
  title: string;
  score: number;
  excerpt: string;
};

export type ChatMessage = {
  message_id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  citations: ChatCitation[];
  action: string | null;
  action_status: "success" | "error" | null;
  action_payload: Record<string, unknown>;
  created_at: string;
};

export type ChatSession = {
  session_id: string;
  incident_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatConversation = {
  session: ChatSession;
  messages: ChatMessage[];
};

const DEFAULT_ORCHESTRATOR_URL = "http://127.0.0.1:8000";

class OrchestratorRequestError extends Error {
  constructor(
    readonly status: number,
    readonly payload: unknown
  ) {
    super(`Orchestrator chat request failed (${status})`);
  }
}

function orchestratorBaseUrl(): string {
  const configuredUrl =
    process.env.ORCHESTRATOR_API_BASE_URL ??
    process.env.NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL ??
    DEFAULT_ORCHESTRATOR_URL;
  return configuredUrl.replace(/\/+$/, "");
}

async function orchestratorRequest<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${orchestratorBaseUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {})
    }
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new OrchestratorRequestError(response.status, payload);
  }

  return payload as T;
}

export async function createChatSession(
  incidentId?: string
): Promise<ChatSession> {
  return orchestratorRequest<ChatSession>("/v1/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ incident_id: incidentId ?? null })
  });
}

export async function listChatSessions(): Promise<ChatSession[]> {
  return orchestratorRequest<ChatSession[]>("/v1/chat/sessions");
}

export async function getChatConversation(
  sessionId: string
): Promise<ChatConversation> {
  return orchestratorRequest<ChatConversation>(
    `/v1/chat/sessions/${encodeURIComponent(sessionId)}`
  );
}

export async function postChatMessage(
  sessionId: string,
  content: string
): Promise<ChatConversation> {
  return orchestratorRequest<ChatConversation>(
    `/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ content })
    }
  );
}

export function toApiError(error: unknown): { status: number; message: string } {
  if (error instanceof OrchestratorRequestError) {
    const detail =
      typeof error.payload === "object" &&
      error.payload !== null &&
      "detail" in error.payload &&
      typeof (error.payload as { detail?: unknown }).detail === "string"
        ? (error.payload as { detail: string }).detail
        : "Chat request failed.";
    return { status: error.status, message: detail };
  }

  return { status: 500, message: "Unexpected chat request failure." };
}
