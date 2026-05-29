import { NextRequest } from "next/server";

export type RequestIdentityHeaders = {
  actorId?: string;
  tenantId?: string;
  fleetId?: string;
  roles?: string[];
  authProvider?: string;
};

export function applyRequestIdentityHeaders(
  headers: Headers,
  identity?: RequestIdentityHeaders
): Headers {
  if (identity?.actorId) headers.set("x-actor-id", identity.actorId);
  if (identity?.tenantId) headers.set("x-tenant-id", identity.tenantId);
  if (identity?.fleetId) headers.set("x-fleet-id", identity.fleetId);
  if (identity?.authProvider) headers.set("x-auth-provider", identity.authProvider);
  if (identity?.roles?.length) headers.set("x-roles", identity.roles.join(","));
  return headers;
}

export function readRequestIdentityHeaders(
  request: NextRequest
): RequestIdentityHeaders | undefined {
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