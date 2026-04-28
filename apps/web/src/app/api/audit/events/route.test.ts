import { describe, expect, it, vi } from "vitest";

const auditMocks = vi.hoisted(() => ({
  listAuditEvents: vi.fn(),
}));

vi.mock("@/lib/incidents", () => ({
  listAuditEvents: auditMocks.listAuditEvents,
}));

import { OrchestratorRequestError } from "@/lib/api";
import { GET } from "./route";

describe("audit events route", () => {
  it("returns all audit events without filters", async () => {
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
    auditMocks.listAuditEvents.mockResolvedValueOnce(events);

    const request = new Request("http://localhost/api/audit/events");
    const response = await GET(request as never);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.events).toHaveLength(1);
  });

  it("passes entity_type and entity_id filters to the lib", async () => {
    auditMocks.listAuditEvents.mockResolvedValueOnce([]);

    const request = new Request(
      "http://localhost/api/audit/events?entity_type=incident&entity_id=inc_abc&limit=10"
    );
    await GET(request as never);

    expect(auditMocks.listAuditEvents).toHaveBeenCalledWith({
      entityType: "incident",
      entityId: "inc_abc",
      limit: 10,
    });
  });

  it("rejects invalid limit values", async () => {
    const request = new Request(
      "http://localhost/api/audit/events?limit=999"
    );
    const response = await GET(request as never);
    expect(response.status).toBe(400);
  });

  it("propagates upstream error status codes", async () => {
    auditMocks.listAuditEvents.mockRejectedValueOnce(
      new OrchestratorRequestError(503, {
        detail: "Service unavailable.",
        error: { code: "service_unavailable", message: "Service unavailable." },
      })
    );

    const request = new Request("http://localhost/api/audit/events");
    const response = await GET(request as never);
    const payload = await response.json();

    expect(response.status).toBe(503);
    expect(payload.error.code).toBe("upstream_error");
  });
});
