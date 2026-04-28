import { describe, expect, it, vi } from "vitest";

const ragUploadMocks = vi.hoisted(() => ({
  uploadRagDocument: vi.fn(),
}));

vi.mock("@/lib/rag", () => ({
  uploadRagDocument: ragUploadMocks.uploadRagDocument,
}));

import { POST } from "./route";

describe("rag upload route", () => {
  it("rejects requests without a file", async () => {
    const formData = new FormData();
    const request = new Request("http://localhost/api/rag/upload", {
      method: "POST",
      body: formData,
    });

    const response = await POST(request as never);
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload).toEqual({
      detail: "A non-empty document file is required.",
      error: {
        code: "invalid_request",
        message: "A non-empty document file is required.",
      },
    });
    expect(ragUploadMocks.uploadRagDocument).not.toHaveBeenCalled();
  });

  it("trims optional fields and returns the ingestion response", async () => {
    ragUploadMocks.uploadRagDocument.mockResolvedValueOnce({
      ok: true,
      data: {
        document_id: "rb_1",
        source: "runbook",
        title: "Battery",
        chunk_count: 2,
        indexed_chunks: 0,
        retrieval_backend: "lexical",
        embedding_provider: "hash",
        embedding_model: "text-embedding-3-large",
        llm_model: "gpt-4o-mini",
      },
    });

    const formData = new FormData();
    formData.append("file", new File(["hello"], "runbook.md", { type: "text/markdown" }));
    formData.append("source", " runbook ");
    formData.append("title", " Battery ");
    formData.append("tags", " battery,thermal ");
    formData.append("chunk_size_chars", " 1200 ");
    formData.append("chunk_overlap_chars", " 200 ");
    const request = new Request("http://localhost/api/rag/upload", {
      method: "POST",
      body: formData,
    });

    const response = await POST(request as never);
    const payload = await response.json();
    const outbound = ragUploadMocks.uploadRagDocument.mock.calls[0][0] as FormData;

    expect(response.status).toBe(201);
    expect(payload.document_id).toBe("rb_1");
    expect(outbound.get("source")).toBe("runbook");
    expect(outbound.get("title")).toBe("Battery");
    expect(outbound.get("tags")).toBe("battery,thermal");
    expect(outbound.get("chunk_size_chars")).toBe("1200");
    expect(outbound.get("chunk_overlap_chars")).toBe("200");
  });

  it("returns the shared error shape when upload returns a typed failure", async () => {
    ragUploadMocks.uploadRagDocument.mockResolvedValueOnce({
      ok: false,
      status: 413,
      message: "Upload exceeds size limit.",
    });

    const formData = new FormData();
    formData.append("file", new File(["hello"], "runbook.md", { type: "text/markdown" }));
    const request = new Request("http://localhost/api/rag/upload", {
      method: "POST",
      body: formData,
    });

    const response = await POST(request as never);
    const payload = await response.json();

    expect(response.status).toBe(413);
    expect(payload).toEqual({
      detail: "Upload exceeds size limit.",
      error: {
        code: "upstream_request_failed",
        message: "Upload exceeds size limit.",
      },
    });
  });
});
