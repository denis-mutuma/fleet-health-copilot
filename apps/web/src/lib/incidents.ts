export type IncidentReport = {
  incident_id: string;
  device_id: string;
  status: "open" | "acknowledged" | "resolved";
  summary: string;
  root_cause_hypotheses: string[];
  recommended_actions: string[];
  evidence: Record<string, string[]>;
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

const DEFAULT_ORCHESTRATOR_URL = "http://127.0.0.1:8000";

function orchestratorBaseUrl(): string {
  const configuredUrl =
    process.env.ORCHESTRATOR_API_BASE_URL ??
    process.env.NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL ??
    DEFAULT_ORCHESTRATOR_URL;
  return configuredUrl.replace(/\/+$/, "");
}

async function orchestratorRequest<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${orchestratorBaseUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    throw new Error(
      `Orchestrator request failed (${response.status}): ${response.statusText}`
    );
  }

  return (await response.json()) as T;
}

export async function listIncidents(): Promise<IncidentReport[]> {
  return orchestratorRequest<IncidentReport[]>("/v1/incidents");
}

export async function getIncident(
  incidentId: string
): Promise<IncidentReport | undefined> {
  const incidents = await listIncidents();
  return incidents.find((incident) => incident.incident_id === incidentId);
}

function buildCanonicalEvent(): TelemetryEvent {
  const suffix = `${Date.now()}`;
  return {
    event_id: `evt_${suffix}`,
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
