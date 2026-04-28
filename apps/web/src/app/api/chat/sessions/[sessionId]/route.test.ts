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

    expect(chatSessionMocks.getChatConversation).toHaveBeenCalledWith("chat_123");
    expect(response.status).toBe(200);
    expect(payload.session.session_id).toBe("chat_123");
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
