import { describe, expect, it, vi } from "vitest";

const incidentMocks = vi.hoisted(() => ({
  listIncidents: vi.fn(),
  orchestrateCanonicalEvent: vi.fn(),
}));

vi.mock("@/lib/incidents", () => ({
  listIncidents: incidentMocks.listIncidents,
  orchestrateCanonicalEvent: incidentMocks.orchestrateCanonicalEvent,
}));

import { OrchestratorRequestError } from "@/lib/api";
import { GET, POST } from "./route";

describe("incidents route", () => {
  it("returns incidents from the orchestrator client", async () => {
    incidentMocks.listIncidents.mockResolvedValueOnce([{ incident_id: "inc_123", status: "open" }]);

    const response = await GET();
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload).toEqual([{ incident_id: "inc_123", status: "open" }]);
  });

  it("preserves upstream status codes in error responses", async () => {
    incidentMocks.listIncidents.mockRejectedValueOnce(
      new OrchestratorRequestError(503, {
        detail: "Orchestrator is unavailable.",
        error: { code: "service_unavailable", message: "Orchestrator is unavailable." },
      })
    );

    const response = await GET();
    const payload = await response.json();

    expect(response.status).toBe(503);
    expect(payload).toEqual({
      detail: "Orchestrator is unavailable.",
      error: {
        code: "upstream_request_failed",
        message: "Orchestrator is unavailable.",
      },
    });
  });

  it("returns 201 for canonical incident orchestration", async () => {
    incidentMocks.orchestrateCanonicalEvent.mockResolvedValueOnce({ incident_id: "inc_456", status: "open" });

    const response = await POST();
    const payload = await response.json();

    expect(response.status).toBe(201);
    expect(payload.incident_id).toBe("inc_456");
  });
});
