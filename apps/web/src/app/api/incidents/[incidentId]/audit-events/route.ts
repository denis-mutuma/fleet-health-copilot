import { NextRequest, NextResponse } from "next/server";
import { apiErrorPayload, toApiError } from "@/lib/api";
import { listIncidentAuditEvents, type IncidentAuditEvent } from "@/lib/incidents";

type RouteContext = {
  params: Promise<{ incidentId: string }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const { incidentId } = await context.params;

  if (!incidentId?.trim()) {
    return NextResponse.json(
      apiErrorPayload("incidentId is required.", "invalid_request"),
      { status: 400 }
    );
  }

  try {
    const events: IncidentAuditEvent[] = await listIncidentAuditEvents(incidentId);
    return NextResponse.json({ events });
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(
      apiErrorPayload(apiError.message, "upstream_error"),
      { status: apiError.status }
    );
  }
}
