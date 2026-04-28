import { OrchestratorRequestError, orchestratorRequest } from "./api";

export { OrchestratorRequestError };

export type IncidentStatus = "open" | "acknowledged" | "resolved";

export type RequestIdentityHeaders = {
  actorId?: string;
  tenantId?: string;
  fleetId?: string;
  roles?: string[];
  authProvider?: string;
};

export type IncidentStatusHistoryEntry = {
  history_id: string;
  incident_id: string;
  previous_status: IncidentStatus | null;
  status: IncidentStatus;
  changed_at: string;
  actor: string;
  source: string;
  reason: string | null;
};

export type IncidentAuditEvent = {
  event_id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor: string;
  source: string;
  occurred_at: string;
  details: Record<string, unknown>;
};

export type IncidentReport = {
  incident_id: string;
  device_id: string;
  status: IncidentStatus;
  summary: string;
  root_cause_hypotheses: string[];
  recommended_actions: string[];
  evidence: Record<string, string[]>;
  confidence_score: number;
  agent_trace: string[];
  verification: {
    passed?: boolean;
    checks?: string[];
    warnings?: string[];
  };
  latency_ms: number;
  status_history: IncidentStatusHistoryEntry[];
  audit_events: IncidentAuditEvent[];
};

type TelemetryEvent = {
  event_id: string;
  fleet_id: string;
  device_id: string;
  timestamp: string;
  metric: string;
  value: number;
  threshold: number;
  severity: "low" | "medium" | "high" | "critical";
  tags: string[];
};

export async function listIncidents(): Promise<IncidentReport[]> {
  return orchestratorRequest<IncidentReport[]>("/v1/incidents");
}

export async function getIncident(
  incidentId: string
): Promise<IncidentReport | undefined> {
  try {
    return await orchestratorRequest<IncidentReport>(
      `/v1/incidents/${encodeURIComponent(incidentId)}`
    );
  } catch (error) {
    if (error instanceof OrchestratorRequestError && error.status === 404) {
      return undefined;
    }
    throw error;
  }
}

export async function updateIncidentStatus(
  incidentId: string,
  status: IncidentStatus,
  reason?: string,
  identity?: RequestIdentityHeaders
): Promise<IncidentReport> {
  const headers = new Headers();
  if (identity?.actorId) headers.set("x-actor-id", identity.actorId);
  if (identity?.tenantId) headers.set("x-tenant-id", identity.tenantId);
  if (identity?.fleetId) headers.set("x-fleet-id", identity.fleetId);
  if (identity?.authProvider) headers.set("x-auth-provider", identity.authProvider);
  if (identity?.roles?.length) headers.set("x-roles", identity.roles.join(","));

  return orchestratorRequest<IncidentReport>(
    `/v1/incidents/${encodeURIComponent(incidentId)}`,
    {
      method: "PATCH",
      headers,
      body: JSON.stringify({ status, ...(reason ? { reason } : {}) })
    }
  );
}

function buildCanonicalEvent(): TelemetryEvent {
  return {
    event_id: `evt_${Date.now()}`,
    fleet_id: "fleet-alpha",
    device_id: "robot-03",
    timestamp: new Date().toISOString(),
    metric: "battery_temp_c",
    value: 74.2,
    threshold: 65.0,
    severity: "high",
    tags: ["battery", "thermal"]
  };
}

export async function orchestrateCanonicalEvent(
  identity?: RequestIdentityHeaders
): Promise<IncidentReport> {
  const headers = new Headers();
  if (identity?.actorId) headers.set("x-actor-id", identity.actorId);
  if (identity?.tenantId) headers.set("x-tenant-id", identity.tenantId);
  if (identity?.fleetId) headers.set("x-fleet-id", identity.fleetId);
  if (identity?.authProvider) headers.set("x-auth-provider", identity.authProvider);
  if (identity?.roles?.length) headers.set("x-roles", identity.roles.join(","));

  return orchestratorRequest<IncidentReport>("/v1/orchestrate/event", {
    method: "POST",
    headers,
    body: JSON.stringify(buildCanonicalEvent())
  });
}
