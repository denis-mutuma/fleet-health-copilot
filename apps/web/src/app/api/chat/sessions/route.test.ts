import { describe, expect, it, vi } from "vitest";

const chatMocks = vi.hoisted(() => ({
  createChatSession: vi.fn(),
  listChatSessions: vi.fn(),
  toApiError: vi.fn(),
}));

vi.mock("@/lib/chat", () => ({
  createChatSession: chatMocks.createChatSession,
  listChatSessions: chatMocks.listChatSessions,
  toApiError: chatMocks.toApiError,
}));

import { GET, POST } from "./route";

describe("chat sessions route", () => {
  it("returns a 400 error payload when incident_id is not a string", async () => {
    const request = new Request("http://localhost/api/chat/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ incident_id: 123 }),
    });

    const response = await POST(request as never);
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload).toEqual({
      detail: "incident_id must be a string when provided.",
      error: {
        code: "invalid_request",
        message: "incident_id must be a string when provided.",
      },
    });
    expect(chatMocks.createChatSession).not.toHaveBeenCalled();
  });

  it("trims incident_id and returns the created session", async () => {
    chatMocks.createChatSession.mockResolvedValueOnce({
      session_id: "chat_123",
      incident_id: "inc_123",
      created_at: "2026-04-28T10:00:00Z",
      updated_at: "2026-04-28T10:00:00Z",
    });

    const request = new Request("http://localhost/api/chat/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ incident_id: "  inc_123  " }),
    });

    const response = await POST(request as never);
    const payload = await response.json();

    expect(chatMocks.createChatSession).toHaveBeenCalledWith("inc_123");
    expect(response.status).toBe(201);
    expect(payload.session_id).toBe("chat_123");
  });

  it("normalizes upstream errors into the shared error shape", async () => {
    chatMocks.listChatSessions.mockRejectedValueOnce(new Error("boom"));
    chatMocks.toApiError.mockReturnValueOnce({ status: 404, message: "Chat session not found." });

    const response = await GET();
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
