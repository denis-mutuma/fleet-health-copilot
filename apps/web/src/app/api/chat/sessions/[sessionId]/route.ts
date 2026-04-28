import { NextRequest, NextResponse } from "next/server";
import { apiErrorPayload } from "@/lib/api";
import { getChatConversation, toApiError } from "@/lib/chat";

type RouteContext = {
  params: Promise<{ sessionId: string }>;
};

export async function GET(_request: NextRequest, context: RouteContext) {
  const { sessionId } = await context.params;

  try {
    const conversation = await getChatConversation(sessionId);
    return NextResponse.json(conversation);
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(
      apiErrorPayload(apiError.message, "upstream_request_failed"),
      { status: apiError.status }
    );
  }
}
