import { NextRequest, NextResponse } from "next/server";
import { apiErrorPayload, toApiError } from "@/lib/api";
import {
  updateIncidentStatus,
  type IncidentStatus
} from "@/lib/incidents";

const INCIDENT_STATUSES = new Set<IncidentStatus>([
  "open",
  "acknowledged",
  "resolved"
]);

type RouteContext = {
  params: Promise<{ incidentId: string }>;
};

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { incidentId } = await context.params;
  const body = (await request.json().catch(() => null)) as {
    status?: unknown;
  } | null;

  if (
    !body ||
    typeof body.status !== "string" ||
    !INCIDENT_STATUSES.has(body.status as IncidentStatus)
  ) {
    return NextResponse.json(
      apiErrorPayload(
        "Incident status must be open, acknowledged, or resolved.",
        "invalid_request"
      ),
      { status: 400 }
    );
  }

  try {
    const incident = await updateIncidentStatus(
      incidentId,
      body.status as IncidentStatus
    );
    return NextResponse.json(incident);
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(
      apiErrorPayload(apiError.message, "upstream_request_failed"),
      { status: apiError.status }
    );
  }
}
