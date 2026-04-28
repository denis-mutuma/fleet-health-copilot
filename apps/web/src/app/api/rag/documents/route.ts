import { NextResponse } from "next/server";
import { apiErrorPayload } from "@/lib/api";
import { listRagDocumentFamilies, toRagApiError } from "@/lib/rag";

export async function GET() {
  try {
    const documents = await listRagDocumentFamilies();
    return NextResponse.json(documents);
  } catch (error) {
    const apiError = toRagApiError(error);
    return NextResponse.json(
      apiErrorPayload(apiError.message, "upstream_request_failed"),
      { status: apiError.status }
    );
  }
}
