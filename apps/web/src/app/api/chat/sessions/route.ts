import { NextRequest, NextResponse } from "next/server";
import { createChatSession, listChatSessions, toApiError } from "@/lib/chat";

export async function GET() {
  try {
    const sessions = await listChatSessions();
    return NextResponse.json(sessions);
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => null)) as {
    incident_id?: unknown;
  } | null;

  if (
    body &&
    "incident_id" in body &&
    body.incident_id !== null &&
    typeof body.incident_id !== "string"
  ) {
    return NextResponse.json(
      { error: "incident_id must be a string when provided." },
      { status: 400 }
    );
  }

  try {
    const session = await createChatSession(
      body?.incident_id && typeof body.incident_id === "string"
        ? body.incident_id.trim() || undefined
        : undefined
    );
    return NextResponse.json(session, { status: 201 });
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}
