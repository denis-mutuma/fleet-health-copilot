"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
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

  async function updateStatus(nextStatus: IncidentStatus) {
    setPendingStatus(nextStatus);
    setErrorMessage(null);

    try {
      const response = await fetch(`/api/incidents/${incidentId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus })
      });

      if (!response.ok) {
        setErrorMessage("Could not update incident status.");
        return;
      }

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
