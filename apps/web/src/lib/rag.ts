import {
  OrchestratorRequestError,
  orchestratorBaseUrl,
  orchestratorRequest,
  readApiErrorMessage,
} from "./api";

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
    const message = readApiErrorMessage(responseBody, "Failed to ingest document.");

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
  return orchestratorRequest<RagDocumentFamily[]>("/v1/rag/documents");
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
    const message = readApiErrorMessage(responseBody, "Failed to delete RAG document family.");

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

export function toRagApiError(error: unknown): { status: number; message: string } {
  if (error instanceof OrchestratorRequestError) {
    return {
      status: error.status,
      message: readApiErrorMessage(error.payload, "Failed to list RAG document families."),
    };
  }
  return { status: 500, message: "Unexpected RAG request failure." };
}
