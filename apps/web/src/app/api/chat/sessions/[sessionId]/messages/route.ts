import { NextRequest, NextResponse } from "next/server";
import { apiErrorPayload } from "@/lib/api";
import { postChatMessage, toApiError } from "@/lib/chat";

type RouteContext = {
  params: Promise<{ sessionId: string }>;
};

export async function POST(request: NextRequest, context: RouteContext) {
  const { sessionId } = await context.params;
  const body = (await request.json().catch(() => null)) as {
    content?: unknown;
  } | null;

  if (!body || typeof body.content !== "string" || !body.content.trim()) {
    return NextResponse.json(
      apiErrorPayload("content must be a non-empty string.", "invalid_request"),
      { status: 400 }
    );
  }

  try {
    const conversation = await postChatMessage(sessionId, body.content.trim());
    return NextResponse.json(conversation);
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(
      apiErrorPayload(apiError.message, "upstream_request_failed"),
      { status: apiError.status }
    );
  }
}
