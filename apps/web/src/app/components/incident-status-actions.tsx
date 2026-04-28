"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { readApiErrorMessage } from "@/lib/api";
import type { IncidentStatus } from "@/lib/incidents";

type IncidentStatusActionsProps = {
  incidentId: string;
  status: IncidentStatus;
};

export default function IncidentStatusActions({
  incidentId,
  status
}: IncidentStatusActionsProps) {
  const router = useRouter();
  const [pendingStatus, setPendingStatus] = useState<IncidentStatus | null>(
    null
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  async function updateStatus(nextStatus: IncidentStatus) {
    setPendingStatus(nextStatus);
    setErrorMessage(null);

    try {
      const response = await fetch(`/api/incidents/${incidentId}`, {
        method: "PATCH",
        headers: {
          "content-type": "application/json"
        },
        body: JSON.stringify({
          status: nextStatus,
          ...(reason.trim() ? { reason: reason.trim() } : {})
        })
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        setErrorMessage(readApiErrorMessage(payload, "Could not update incident status."));
        return;
      }

      setReason("");
      router.refresh();
    } catch {
      setErrorMessage("Could not update incident status.");
    } finally {
      setPendingStatus(null);
    }
  }

  if (status === "resolved") {
    return (
      <div className="actions-panel">
        <p className="muted">This incident is resolved.</p>
      </div>
    );
  }

  return (
    <div className="actions-panel">
      <label className="incident-note-field">
        <span className="sidebar-label">Operator note</span>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Capture why the status changed, handoff context, or verification notes."
          rows={3}
        />
      </label>
      <div className="actions action-group-tight">
        {status === "open" ? (
          <button
            className="button secondary-button"
            disabled={pendingStatus !== null}
            onClick={() => updateStatus("acknowledged")}
          >
            {pendingStatus === "acknowledged" ? "Acknowledging..." : "Acknowledge"}
          </button>
        ) : null}
        <button
          className="button"
          disabled={pendingStatus !== null}
          onClick={() => updateStatus("resolved")}
        >
          {pendingStatus === "resolved" ? "Resolving..." : "Resolve incident"}
        </button>
      </div>
      {errorMessage ? <p className="error">{errorMessage}</p> : null}
    </div>
  );
}
