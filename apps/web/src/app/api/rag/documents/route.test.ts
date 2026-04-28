import { describe, expect, it, vi } from "vitest";

const ragDocumentMocks = vi.hoisted(() => ({
  listRagDocumentFamilies: vi.fn(),
  toRagApiError: vi.fn(),
}));

vi.mock("@/lib/rag", () => ({
  listRagDocumentFamilies: ragDocumentMocks.listRagDocumentFamilies,
  toRagApiError: ragDocumentMocks.toRagApiError,
}));

import { GET } from "./route";

describe("rag documents route", () => {
  it("returns document families from the rag client", async () => {
    ragDocumentMocks.listRagDocumentFamilies.mockResolvedValueOnce([
      { document_id: "rb_1", title: "Battery", source: "runbook", tags: [], chunk_count: 2 },
    ]);

    const response = await GET();
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload).toHaveLength(1);
    expect(payload[0].document_id).toBe("rb_1");
  });

  it("returns a shared error payload when the rag client fails", async () => {
    ragDocumentMocks.listRagDocumentFamilies.mockRejectedValueOnce(new Error("boom"));
    ragDocumentMocks.toRagApiError.mockReturnValueOnce({
      status: 503,
      message: "Repository check failed.",
    });

    const response = await GET();
    const payload = await response.json();

    expect(response.status).toBe(503);
    expect(payload).toEqual({
      detail: "Repository check failed.",
      error: {
        code: "upstream_request_failed",
        message: "Repository check failed.",
      },
    });
  });
});
