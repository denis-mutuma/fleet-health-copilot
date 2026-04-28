import { describe, expect, it, vi } from "vitest";

const chatMessageMocks = vi.hoisted(() => ({
  postChatMessage: vi.fn(),
  toApiError: vi.fn(),
}));

vi.mock("@/lib/chat", () => ({
  postChatMessage: chatMessageMocks.postChatMessage,
  toApiError: chatMessageMocks.toApiError,
}));

import { POST } from "./route";

describe("chat messages route", () => {
  it("rejects empty message content before calling the client", async () => {
    const request = new Request("http://localhost/api/chat/sessions/chat_123/messages", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content: "   " }),
    });

    const response = await POST(request as never, {
      params: Promise.resolve({ sessionId: "chat_123" }),
    });
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload).toEqual({
      detail: "content must be a non-empty string.",
      error: {
        code: "invalid_request",
        message: "content must be a non-empty string.",
      },
    });
    expect(chatMessageMocks.postChatMessage).not.toHaveBeenCalled();
  });

  it("trims content and returns the updated conversation", async () => {
    chatMessageMocks.postChatMessage.mockResolvedValueOnce({
      session: { session_id: "chat_123", incident_id: null },
      messages: [{ message_id: "msg_1", content: "ok" }],
    });

    const request = new Request("http://localhost/api/chat/sessions/chat_123/messages", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content: "  hello  " }),
    });

    const response = await POST(request as never, {
      params: Promise.resolve({ sessionId: "chat_123" }),
    });
    const payload = await response.json();

    expect(chatMessageMocks.postChatMessage).toHaveBeenCalledWith("chat_123", "hello");
    expect(response.status).toBe(200);
    expect(payload.messages).toHaveLength(1);
  });

  it("uses the shared error shape for upstream failures", async () => {
    chatMessageMocks.postChatMessage.mockRejectedValueOnce(new Error("boom"));
    chatMessageMocks.toApiError.mockReturnValueOnce({ status: 404, message: "Chat session not found." });

    const request = new Request("http://localhost/api/chat/sessions/chat_missing/messages", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content: "hello" }),
    });

    const response = await POST(request as never, {
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
