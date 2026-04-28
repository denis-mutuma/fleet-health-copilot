import { describe, expect, it, vi } from "vitest";

const auditMocks = vi.hoisted(() => ({
  listIncidentAuditEvents: vi.fn(),
}));

vi.mock("@/lib/incidents", () => ({
  listIncidentAuditEvents: auditMocks.listIncidentAuditEvents,
}));

import { OrchestratorRequestError } from "@/lib/api";
import { GET } from "./route";

function makeContext(incidentId: string) {
  return { params: Promise.resolve({ incidentId }) };
}

describe("incident audit-events route", () => {
  it("returns audit events for a valid incident", async () => {
    const events = [
      {
        event_id: "evt_1",
        entity_type: "incident",
        entity_id: "inc_123",
        action: "incident.created",
        actor: "system",
        source: "orchestrator",
        occurred_at: "2024-01-01T00:00:00Z",
        details: {},
      },
    ];
    auditMocks.listIncidentAuditEvents.mockResolvedValueOnce(events);

    const request = new Request(
      "http://localhost/api/incidents/inc_123/audit-events"
    );
    const response = await GET(request as never, makeContext("inc_123"));
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.events).toHaveLength(1);
    expect(payload.events[0].event_id).toBe("evt_1");
  });

  it("propagates upstream error status codes", async () => {
    auditMocks.listIncidentAuditEvents.mockRejectedValueOnce(
      new OrchestratorRequestError(404, {
        detail: "Incident not found.",
        error: { code: "not_found", message: "Incident not found." },
      })
    );

    const request = new Request(
      "http://localhost/api/incidents/missing/audit-events"
    );
    const response = await GET(request as never, makeContext("missing"));
    const payload = await response.json();

    expect(response.status).toBe(404);
    expect(payload.error.code).toBe("upstream_error");
    expect(payload.detail).toBe("Incident not found.");
  });
});
