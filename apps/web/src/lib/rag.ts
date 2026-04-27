export type RagIngestionResponse = {
  document_id: string;
  source: string;
  title: string;
  chunk_count: number;
  indexed_chunks: number;
  retrieval_backend: string;
  embedding_provider: string;
  embedding_model: string;
  llm_model: string;
};

export type RagDocumentFamily = {
  document_id: string;
  source: string;
  title: string;
  tags: string[];
  chunk_count: number;
};

const DEFAULT_ORCHESTRATOR_URL = "http://127.0.0.1:8000";

function orchestratorBaseUrl(): string {
  const configuredUrl =
    process.env.ORCHESTRATOR_API_BASE_URL ??
    process.env.NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL ??
    DEFAULT_ORCHESTRATOR_URL;
  return configuredUrl.replace(/\/+$/, "");
}

export async function uploadRagDocument(
  payload: FormData
): Promise<{ ok: true; data: RagIngestionResponse } | { ok: false; status: number; message: string }> {
  const response = await fetch(`${orchestratorBaseUrl()}/v1/rag/documents/upload`, {
    method: "POST",
    body: payload,
    cache: "no-store"
  });

  let responseBody: unknown = null;
  try {
    responseBody = await response.json();
  } catch {
    responseBody = null;
  }

  if (!response.ok) {
    const message =
      typeof responseBody === "object" &&
      responseBody !== null &&
      "detail" in responseBody &&
      typeof (responseBody as { detail?: unknown }).detail === "string"
        ? (responseBody as { detail: string }).detail
        : "Failed to ingest document.";

    return {
      ok: false,
      status: response.status,
      message
    };
  }

  return {
    ok: true,
    data: responseBody as RagIngestionResponse
  };
}

export async function listRagDocumentFamilies(): Promise<RagDocumentFamily[]> {
  const response = await fetch(`${orchestratorBaseUrl()}/v1/rag/documents`, {
    method: "GET",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("Failed to list RAG document families.");
  }

  return (await response.json()) as RagDocumentFamily[];
}

export async function deleteRagDocumentFamily(
  documentId: string
): Promise<{ ok: true; deletedChunks: number } | { ok: false; status: number; message: string }> {
  const response = await fetch(
    `${orchestratorBaseUrl()}/v1/rag/documents/${encodeURIComponent(documentId)}`,
    {
      method: "DELETE",
      cache: "no-store"
    }
  );

  let responseBody: unknown = null;
  try {
    responseBody = await response.json();
  } catch {
    responseBody = null;
  }

  if (!response.ok) {
    const message =
      typeof responseBody === "object" &&
      responseBody !== null &&
      "detail" in responseBody &&
      typeof (responseBody as { detail?: unknown }).detail === "string"
        ? (responseBody as { detail: string }).detail
        : "Failed to delete RAG document family.";

    return {
      ok: false,
      status: response.status,
      message
    };
  }

  const deletedChunks =
    typeof responseBody === "object" &&
    responseBody !== null &&
    "deleted_chunks" in responseBody &&
    typeof (responseBody as { deleted_chunks?: unknown }).deleted_chunks === "number"
      ? (responseBody as { deleted_chunks: number }).deleted_chunks
      : 0;

  return {
    ok: true,
    deletedChunks
  };
}
