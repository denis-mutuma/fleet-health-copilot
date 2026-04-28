import { NextRequest, NextResponse } from "next/server";
import { apiErrorPayload, toApiError } from "@/lib/api";
import {
  listIncidents,
  orchestrateCanonicalEvent,
  type RequestIdentityHeaders
} from "@/lib/incidents";

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

export async function GET() {
  try {
    const incidents = await listIncidents();
    return NextResponse.json(incidents);
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(
      apiErrorPayload(apiError.message, "upstream_request_failed"),
      { status: apiError.status }
    );
  }
}

export async function POST(request: NextRequest) {
  const identity = readIdentityHeaders(request);
  try {
    const incident = await orchestrateCanonicalEvent(identity);
    return NextResponse.json(incident, { status: 201 });
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(
      apiErrorPayload(apiError.message, "upstream_request_failed"),
      { status: apiError.status }
    );
  }
}
