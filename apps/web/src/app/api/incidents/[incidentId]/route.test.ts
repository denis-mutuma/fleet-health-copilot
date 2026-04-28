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

    expect(incidentStatusMocks.updateIncidentStatus).toHaveBeenCalledWith(
      "inc_missing",
      "acknowledged",
      undefined,
      undefined
    );
    expect(response.status).toBe(404);
    expect(payload).toEqual({
      detail: "Incident not found.",
      error: {
        code: "upstream_request_failed",
        message: "Incident not found.",
      },
    });
  });

  it("accepts an optional audit reason and forwards it", async () => {
    incidentStatusMocks.updateIncidentStatus.mockResolvedValueOnce({
      incident_id: "inc_123",
      status: "resolved",
      status_history: [],
      audit_events: [],
    });

    const request = new Request("http://localhost/api/incidents/inc_123", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status: "resolved", reason: "Operator confirmed recovery." }),
    });

    const response = await PATCH(request as never, {
      params: Promise.resolve({ incidentId: "inc_123" }),
    });

    expect(response.status).toBe(200);
    expect(incidentStatusMocks.updateIncidentStatus).toHaveBeenCalledWith(
      "inc_123",
      "resolved",
      "Operator confirmed recovery.",
      undefined
    );
  });

  it("rejects blank audit reasons", async () => {
    const request = new Request("http://localhost/api/incidents/inc_123", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status: "resolved", reason: "   " }),
    });

    const response = await PATCH(request as never, {
      params: Promise.resolve({ incidentId: "inc_123" }),
    });
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload).toEqual({
      detail: "Incident reason must be a non-empty string when provided.",
      error: {
        code: "invalid_request",
        message: "Incident reason must be a non-empty string when provided.",
      },
    });
  });

  it("forwards identity headers when provided", async () => {
    incidentStatusMocks.updateIncidentStatus.mockResolvedValueOnce({
      incident_id: "inc_123",
      status: "acknowledged",
      status_history: [],
      audit_events: [],
    });

    const request = new Request("http://localhost/api/incidents/inc_123", {
      method: "PATCH",
      headers: {
        "content-type": "application/json",
        "x-actor-id": "usr_2",
        "x-tenant-id": "tenant_99",
        "x-roles": "operator",
      },
      body: JSON.stringify({ status: "acknowledged" }),
    });

    const response = await PATCH(request as never, {
      params: Promise.resolve({ incidentId: "inc_123" }),
    });

    expect(response.status).toBe(200);
    expect(incidentStatusMocks.updateIncidentStatus).toHaveBeenCalledWith(
      "inc_123",
      "acknowledged",
      undefined,
      {
        actorId: "usr_2",
        tenantId: "tenant_99",
        fleetId: undefined,
        authProvider: undefined,
        roles: ["operator"],
      }
    );
  });
});
