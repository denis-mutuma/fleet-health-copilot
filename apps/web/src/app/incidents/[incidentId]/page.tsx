import Link from "next/link";
import { notFound } from "next/navigation";
import { getIncident, type IncidentReport } from "@/lib/incidents";
import IncidentStatusActions from "@/app/components/incident-status-actions";

function statusLabel(status: IncidentReport["status"]): string {
  return status.toUpperCase();
}

export default async function IncidentDetailPage({
  params
}: {
  params: Promise<{ incidentId: string }>;
}) {
  const { incidentId } = await params;
  let incident: IncidentReport | undefined;

  try {
    incident = await getIncident(incidentId);
  } catch {
    return (
      <main className="container">
        <header className="hero">
          <p className="eyebrow">Incident report</p>
          <h1>Service unavailable</h1>
          <p className="error">
            Could not load incident data because the orchestrator is
            unavailable.
          </p>
          <p>
            <Link href="/">Back to dashboard</Link>
          </p>
        </header>
      </main>
    );
  }

  if (!incident) {
    notFound();
  }

  return (
    <main className="container">
      <header className="hero">
        <p className="eyebrow">Incident report</p>
        <h1>{incident.incident_id}</h1>
        <p>
          Device: <strong>{incident.device_id}</strong>{" "}
          <span className={`status-badge status-${incident.status}`}>
            {statusLabel(incident.status)}
          </span>
        </p>
        <p>{incident.summary}</p>
        <div className="report-metadata">
          <span>Confidence {(incident.confidence_score * 100).toFixed(0)}%</span>
          <span>Diagnosis {incident.latency_ms.toFixed(1)} ms</span>
          <span>
            Verification{" "}
            {incident.verification.passed === false ? "flagged" : "passed"}
          </span>
        </div>
        <IncidentStatusActions
          incidentId={incident.incident_id}
          status={incident.status}
        />
        <p>
          <Link href={`/chat?incidentId=${encodeURIComponent(incident.incident_id)}`}>
            Open chat for this incident
          </Link>
        </p>
        <p>
          <Link href="/">Back to dashboard</Link>
        </p>
      </header>

      <section className="card">
        <h2>Root cause hypotheses</h2>
        <ul>
          {incident.root_cause_hypotheses.map((item, idx) => (
            <li key={`hypothesis-${idx}`}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Recommended actions</h2>
        <ul>
          {incident.recommended_actions.map((item, idx) => (
            <li key={`action-${idx}`}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Agent trace</h2>
        <ol className="timeline-list">
          {incident.agent_trace.map((item, idx) => (
            <li key={`trace-${idx}`}>{item}</li>
          ))}
        </ol>
      </section>

      <section className="card">
        <h2>Verification</h2>
        <ul>
          {(incident.verification.checks ?? []).map((check, idx) => (
            <li key={`check-${idx}`}>{check}</li>
          ))}
        </ul>
        {(incident.verification.warnings ?? []).length > 0 ? (
          <div className="warning-box">
            <strong>Warnings</strong>
            <ul>
              {(incident.verification.warnings ?? []).map((warning, idx) => (
                <li key={`warning-${idx}`}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="card">
        <h2>Evidence</h2>
        <div className="evidence-grid">
          {Object.entries(incident.evidence).map(([key, values], idx) => (
            <div key={`evidence-${idx}`} className="evidence-group">
              <h3>{key.replaceAll("_", " ")}</h3>
              {values.length === 0 ? (
                <p className="muted">No matches</p>
              ) : (
                <ul>
                  {values.map((value, valIdx) => (
                    <li key={`evidence-${idx}-${valIdx}`}>{value}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
