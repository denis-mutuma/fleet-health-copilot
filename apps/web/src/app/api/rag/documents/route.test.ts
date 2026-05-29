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

    const response = await GET(new Request("http://localhost/api/rag/documents") as never);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload).toHaveLength(1);
    expect(payload[0].document_id).toBe("rb_1");
    expect(ragDocumentMocks.listRagDocumentFamilies).toHaveBeenCalledWith(undefined);
  });

  it("forwards identity headers to rag document listing", async () => {
    ragDocumentMocks.listRagDocumentFamilies.mockResolvedValueOnce([]);

    await GET(
      new Request("http://localhost/api/rag/documents", {
        headers: {
          "x-actor-id": "usr_5",
          "x-tenant-id": "tenant_5",
          "x-roles": "operator",
        },
      }) as never
    );

    expect(ragDocumentMocks.listRagDocumentFamilies).toHaveBeenCalledWith({
      actorId: "usr_5",
      tenantId: "tenant_5",
      fleetId: undefined,
      authProvider: undefined,
      roles: ["operator"],
    });
  });

  it("returns a shared error payload when the rag client fails", async () => {
    ragDocumentMocks.listRagDocumentFamilies.mockRejectedValueOnce(new Error("boom"));
    ragDocumentMocks.toRagApiError.mockReturnValueOnce({
      status: 503,
      message: "Repository check failed.",
    });

    const response = await GET(new Request("http://localhost/api/rag/documents") as never);
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
