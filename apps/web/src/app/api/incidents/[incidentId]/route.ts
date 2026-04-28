import { NextRequest, NextResponse } from "next/server";
import { apiErrorPayload, toApiError } from "@/lib/api";
import {
  type RequestIdentityHeaders,
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

function readIdentityHeaders(request: NextRequest): RequestIdentityHeaders | undefined {
  const actorId = request.headers.get("x-actor-id")?.trim();
  const tenantId = request.headers.get("x-tenant-id")?.trim();
  const fleetId = request.headers.get("x-fleet-id")?.trim();
  const authProvider = request.headers.get("x-auth-provider")?.trim();
  const rolesHeader = request.headers.get("x-roles")?.trim();

  const roles = rolesHeader
    ? rolesHeader
        .split(",")
        .map((role) => role.trim())
        .filter(Boolean)
    : [];

  const identity: RequestIdentityHeaders = {
    actorId: actorId || undefined,
    tenantId: tenantId || undefined,
    fleetId: fleetId || undefined,
    authProvider: authProvider || undefined,
    roles: roles.length > 0 ? roles : undefined,
  };

  const hasIdentity =
    Boolean(identity.actorId) ||
    Boolean(identity.tenantId) ||
    Boolean(identity.fleetId) ||
    Boolean(identity.authProvider) ||
    Boolean(identity.roles?.length);

  return hasIdentity ? identity : undefined;
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { incidentId } = await context.params;
  const identity = readIdentityHeaders(request);
  const body = (await request.json().catch(() => null)) as {
    status?: unknown;
    reason?: unknown;
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

  if (
    body.reason !== undefined &&
    (typeof body.reason !== "string" || !body.reason.trim())
  ) {
    return NextResponse.json(
      apiErrorPayload("Incident reason must be a non-empty string when provided.", "invalid_request"),
      { status: 400 }
    );
  }

  try {
    const incident = await updateIncidentStatus(
      incidentId,
      body.status as IncidentStatus,
      typeof body.reason === "string" ? body.reason.trim() : undefined,
      identity
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
