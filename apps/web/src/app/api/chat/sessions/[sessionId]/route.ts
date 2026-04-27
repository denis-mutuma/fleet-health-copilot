import { NextRequest, NextResponse } from "next/server";
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
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}
