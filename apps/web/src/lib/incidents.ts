import { OrchestratorRequestError, orchestratorRequest } from "./api";

export { OrchestratorRequestError };

export type IncidentStatus = "open" | "acknowledged" | "resolved";

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
  status: IncidentStatus
): Promise<IncidentReport> {
  return orchestratorRequest<IncidentReport>(
    `/v1/incidents/${encodeURIComponent(incidentId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ status })
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

export async function orchestrateCanonicalEvent(): Promise<IncidentReport> {
  return orchestratorRequest<IncidentReport>("/v1/orchestrate/event", {
    method: "POST",
    body: JSON.stringify(buildCanonicalEvent())
  });
}
