import { describe, expect, it, vi } from "vitest";

const chatSessionMocks = vi.hoisted(() => ({
  getChatConversation: vi.fn(),
  toApiError: vi.fn(),
}));

vi.mock("@/lib/chat", () => ({
  getChatConversation: chatSessionMocks.getChatConversation,
  toApiError: chatSessionMocks.toApiError,
}));

import { GET } from "./route";

describe("chat session detail route", () => {
  it("returns the conversation for the provided session id", async () => {
    chatSessionMocks.getChatConversation.mockResolvedValueOnce({
      session: { session_id: "chat_123", incident_id: null },
      messages: [],
    });

    const request = new Request("http://localhost/api/chat/sessions/chat_123");
    const response = await GET(request as never, {
      params: Promise.resolve({ sessionId: "chat_123" }),
    });
    const payload = await response.json();

    expect(chatSessionMocks.getChatConversation).toHaveBeenCalledWith("chat_123", undefined);
    expect(response.status).toBe(200);
    expect(payload.session.session_id).toBe("chat_123");
  });

  it("forwards identity headers to chat conversation lookup", async () => {
    chatSessionMocks.getChatConversation.mockResolvedValueOnce({
      session: { session_id: "chat_123", incident_id: null },
      messages: [],
    });

    const request = new Request("http://localhost/api/chat/sessions/chat_123", {
      headers: {
        "x-actor-id": "usr_2",
        "x-tenant-id": "tenant_7",
        "x-roles": "operator",
      },
    });

    await GET(request as never, {
      params: Promise.resolve({ sessionId: "chat_123" }),
    });

    expect(chatSessionMocks.getChatConversation).toHaveBeenCalledWith("chat_123", {
      actorId: "usr_2",
      tenantId: "tenant_7",
      fleetId: undefined,
      authProvider: undefined,
      roles: ["operator"],
    });
  });

  it("uses the shared error shape for upstream failures", async () => {
    chatSessionMocks.getChatConversation.mockRejectedValueOnce(new Error("boom"));
    chatSessionMocks.toApiError.mockReturnValueOnce({
      status: 404,
      message: "Chat session not found.",
    });

    const request = new Request("http://localhost/api/chat/sessions/chat_missing");
    const response = await GET(request as never, {
      params: Promise.resolve({ sessionId: "chat_missing" }),
    });
    const payload = await response.json();

    expect(response.status).toBe(404);
    expect(payload).toEqual({
      detail: "Chat session not found.",
      error: {
        code: "upstream_request_failed",
        message: "Chat session not found.",
      },
    });
  });
});
