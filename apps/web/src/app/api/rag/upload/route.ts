import { NextRequest, NextResponse } from "next/server";
import { apiErrorPayload } from "@/lib/api";
import { uploadRagDocument } from "@/lib/rag";

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  const file = formData.get("file");

  if (!(file instanceof File) || file.size === 0) {
    return NextResponse.json(
      apiErrorPayload("A non-empty document file is required.", "invalid_request"),
      { status: 400 }
    );
  }

  const source = formData.get("source");
  const title = formData.get("title");
  const tags = formData.get("tags");
  const chunkSizeChars = formData.get("chunk_size_chars");
  const chunkOverlapChars = formData.get("chunk_overlap_chars");

  const outbound = new FormData();
  outbound.append("file", file, file.name);
  if (typeof source === "string" && source.trim()) {
    outbound.append("source", source.trim());
  }
  if (typeof title === "string" && title.trim()) {
    outbound.append("title", title.trim());
  }
  if (typeof tags === "string" && tags.trim()) {
    outbound.append("tags", tags.trim());
  }
  if (typeof chunkSizeChars === "string" && chunkSizeChars.trim()) {
    outbound.append("chunk_size_chars", chunkSizeChars.trim());
  }
  if (typeof chunkOverlapChars === "string" && chunkOverlapChars.trim()) {
    outbound.append("chunk_overlap_chars", chunkOverlapChars.trim());
  }

  try {
    const result = await uploadRagDocument(outbound);
    if (!result.ok) {
      return NextResponse.json(
        apiErrorPayload(result.message, "upstream_request_failed"),
        { status: result.status }
      );
    }

    return NextResponse.json(result.data, { status: 201 });
  } catch {
    return NextResponse.json(
      apiErrorPayload("Could not upload and ingest document.", "upstream_request_failed"),
      { status: 502 }
    );
  }
}
