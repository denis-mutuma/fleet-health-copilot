import { NextRequest, NextResponse } from "next/server";
import { apiErrorPayload } from "@/lib/api";
import { deleteRagDocumentFamily } from "@/lib/rag";
import { readRequestIdentityHeaders } from "@/lib/request-identity";

type RouteContext = {
  params: Promise<{ documentId: string }>;
};

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { documentId } = await context.params;
  const identity = readRequestIdentityHeaders(request);

  try {
    const result = await deleteRagDocumentFamily(documentId, identity);
    if (!result.ok) {
      return NextResponse.json(
        apiErrorPayload(result.message, "upstream_request_failed"),
        { status: result.status }
      );
    }

    return NextResponse.json({ document_id: documentId, deleted_chunks: result.deletedChunks });
  } catch {
    return NextResponse.json(
      apiErrorPayload("Could not delete RAG document.", "upstream_request_failed"),
      { status: 502 }
    );
  }
}
