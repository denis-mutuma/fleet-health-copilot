import { NextRequest, NextResponse } from "next/server";
import { apiErrorPayload, toApiError } from "@/lib/api";
import { listAuditEvents, type IncidentAuditEvent } from "@/lib/incidents";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const entityType = searchParams.get("entity_type") ?? undefined;
  const entityId = searchParams.get("entity_id") ?? undefined;
  const limitRaw = searchParams.get("limit");
  const limit = limitRaw ? parseInt(limitRaw, 10) : undefined;

  if (limit !== undefined && (isNaN(limit) || limit < 1 || limit > 500)) {
    return NextResponse.json(
      apiErrorPayload("limit must be an integer between 1 and 500.", "invalid_request"),
      { status: 400 }
    );
  }

  try {
    const events: IncidentAuditEvent[] = await listAuditEvents({
      entityType,
      entityId,
      limit,
    });
    return NextResponse.json({ events });
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(
      apiErrorPayload(apiError.message, "upstream_error"),
      { status: apiError.status }
    );
  }
}
