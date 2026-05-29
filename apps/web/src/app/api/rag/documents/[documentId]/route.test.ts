import { describe, expect, it, vi } from "vitest";

const ragDeleteMocks = vi.hoisted(() => ({
  deleteRagDocumentFamily: vi.fn(),
}));

vi.mock("@/lib/rag", () => ({
  deleteRagDocumentFamily: ragDeleteMocks.deleteRagDocumentFamily,
}));

import { DELETE } from "./route";

describe("rag document delete route", () => {
  it("returns deleted chunk metadata on success", async () => {
    ragDeleteMocks.deleteRagDocumentFamily.mockResolvedValueOnce({ ok: true, deletedChunks: 4 });

    const request = new Request("http://localhost/api/rag/documents/rb_1", { method: "DELETE" });
    const response = await DELETE(request as never, {
      params: Promise.resolve({ documentId: "rb_1" }),
    });
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload).toEqual({ document_id: "rb_1", deleted_chunks: 4 });
    expect(ragDeleteMocks.deleteRagDocumentFamily).toHaveBeenCalledWith("rb_1", undefined);
  });

  it("forwards identity headers to rag document deletion", async () => {
    ragDeleteMocks.deleteRagDocumentFamily.mockResolvedValueOnce({ ok: true, deletedChunks: 1 });

    const request = new Request("http://localhost/api/rag/documents/rb_1", {
      method: "DELETE",
      headers: {
        "x-actor-id": "usr_6",
        "x-tenant-id": "tenant_6",
        "x-roles": "admin",
      },
    });

    await DELETE(request as never, {
      params: Promise.resolve({ documentId: "rb_1" }),
    });

    expect(ragDeleteMocks.deleteRagDocumentFamily).toHaveBeenCalledWith("rb_1", {
      actorId: "usr_6",
      tenantId: "tenant_6",
      fleetId: undefined,
      authProvider: undefined,
      roles: ["admin"],
    });
  });

  it("returns the shared error shape when the rag client returns a typed failure", async () => {
    ragDeleteMocks.deleteRagDocumentFamily.mockResolvedValueOnce({
      ok: false,
      status: 404,
      message: "Document not found.",
    });

    const request = new Request("http://localhost/api/rag/documents/rb_missing", { method: "DELETE" });
    const response = await DELETE(request as never, {
      params: Promise.resolve({ documentId: "rb_missing" }),
    });
    const payload = await response.json();

    expect(response.status).toBe(404);
    expect(payload).toEqual({
      detail: "Document not found.",
      error: {
        code: "upstream_request_failed",
        message: "Document not found.",
      },
    });
  });
});
