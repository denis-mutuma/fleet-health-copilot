import { describe, expect, it, vi } from "vitest";

const incidentStatusMocks = vi.hoisted(() => ({
  updateIncidentStatus: vi.fn(),
}));

vi.mock("@/lib/incidents", () => ({
  updateIncidentStatus: incidentStatusMocks.updateIncidentStatus,
}));

import { OrchestratorRequestError } from "@/lib/api";
import { PATCH } from "./route";

describe("incident status route", () => {
  it("rejects invalid status values before calling the orchestrator client", async () => {
    const request = new Request("http://localhost/api/incidents/inc_123", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status: "closed" }),
    });

    const response = await PATCH(request as never, {
      params: Promise.resolve({ incidentId: "inc_123" }),
    });
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload).toEqual({
      detail: "Incident status must be open, acknowledged, or resolved.",
      error: {
        code: "invalid_request",
        message: "Incident status must be open, acknowledged, or resolved.",
      },
    });
    expect(incidentStatusMocks.updateIncidentStatus).not.toHaveBeenCalled();
  });

  it("passes through upstream not-found errors using the shared shape", async () => {
    incidentStatusMocks.updateIncidentStatus.mockRejectedValueOnce(
      new OrchestratorRequestError(404, {
        detail: "Incident not found.",
        error: { code: "resource_not_found", message: "Incident not found." },
      })
    );

    const request = new Request("http://localhost/api/incidents/inc_missing", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status: "acknowledged" }),
    });

    const response = await PATCH(request as never, {
      params: Promise.resolve({ incidentId: "inc_missing" }),
    });
    const payload = await response.json();

    expect(incidentStatusMocks.updateIncidentStatus).toHaveBeenCalledWith("inc_missing", "acknowledged");
    expect(response.status).toBe(404);
    expect(payload).toEqual({
      detail: "Incident not found.",
      error: {
        code: "upstream_request_failed",
        message: "Incident not found.",
      },
    });
  });
});
