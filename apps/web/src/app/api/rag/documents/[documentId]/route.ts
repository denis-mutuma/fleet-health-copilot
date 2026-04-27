import { NextRequest, NextResponse } from "next/server";
import { deleteRagDocumentFamily } from "@/lib/rag";

type RouteContext = {
  params: Promise<{ documentId: string }>;
};

export async function DELETE(_request: NextRequest, context: RouteContext) {
  const { documentId } = await context.params;

  try {
    const result = await deleteRagDocumentFamily(documentId);
    if (!result.ok) {
      return NextResponse.json(
        { error: result.message },
        { status: result.status }
      );
    }

    return NextResponse.json({ document_id: documentId, deleted_chunks: result.deletedChunks });
  } catch {
    return NextResponse.json(
      { error: "Could not delete RAG document." },
      { status: 502 }
    );
  }
}
