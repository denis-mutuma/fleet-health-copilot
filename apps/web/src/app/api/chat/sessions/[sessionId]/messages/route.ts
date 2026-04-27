import { NextRequest, NextResponse } from "next/server";
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
      { error: "content must be a non-empty string." },
      { status: 400 }
    );
  }

  try {
    const conversation = await postChatMessage(sessionId, body.content.trim());
    return NextResponse.json(conversation);
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}
