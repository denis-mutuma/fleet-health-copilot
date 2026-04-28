import {
  OrchestratorRequestError,
  orchestratorRequest,
  toApiError as sharedToApiError
} from "./api";

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
  tool_calls?: Array<{
    tool_name: string;
    input: Record<string, unknown>;
    output: Record<string, unknown>;
    latency_ms: number;
    error?: string | null;
  }>;
  trace_spans?: Array<{
    span_name: string;
    status: "success" | "error" | "skipped";
    latency_ms: number;
    metadata: Record<string, unknown>;
    error?: string | null;
  }>;
  llm_cost_usd?: number | null;
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
  const shared = sharedToApiError(error);
  if (shared.status !== 500) {
    return shared;
  }

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
