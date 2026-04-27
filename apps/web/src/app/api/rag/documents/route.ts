import { NextResponse } from "next/server";
import { listRagDocumentFamilies } from "@/lib/rag";

export async function GET() {
  try {
    const documents = await listRagDocumentFamilies();
    return NextResponse.json(documents);
  } catch {
    return NextResponse.json(
      { error: "Could not load RAG corpus." },
      { status: 502 }
    );
  }
}
