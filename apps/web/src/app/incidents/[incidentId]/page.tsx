import Link from "next/link";
import { notFound } from "next/navigation";
import { getIncident, type IncidentReport } from "@/lib/incidents";
import IncidentStatusActions from "@/app/components/incident-status-actions";

function statusLabel(status: IncidentReport["status"]): string {
  const normalized = status.replace("_", " ");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString();
}

function auditDetailSummary(details: Record<string, unknown>): string[] {
  return Object.entries(details).map(([key, value]) => {
    const normalizedKey = key.replaceAll("_", " ");
    const normalizedValue = Array.isArray(value) ? value.join(", ") : String(value);
    return `${normalizedKey}: ${normalizedValue}`;
  });
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
    <main className="container page-grid">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Operations</Link>
        <span aria-hidden="true">/</span>
        <span>Incident investigation</span>
        <span aria-hidden="true">/</span>
        <span className="mono" aria-current="page">{incident.incident_id}</span>
      </nav>

      <header className="hero">
        <p className="eyebrow">Incident investigation</p>
        <h1>{incident.summary}</h1>
        <p>
          Device <strong>{incident.device_id}</strong> is currently tracked under
          <span className={`status-badge status-${incident.status}`}> {statusLabel(incident.status)}</span>
          . Review evidence, verify the reasoning chain, and coordinate action from chat.
        </p>
        <div className="report-metadata">
          <span className="mono">{incident.incident_id}</span>
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
        <div className="actions action-group">
          <Link
            href={`/chat?incidentId=${encodeURIComponent(incident.incident_id)}`}
            className="button rag-link-button"
          >
            Open chat for this incident
          </Link>
          <Link href="/" className="secondary-button rag-link-button">
            Back to dashboard
          </Link>
        </div>
      </header>

      <section className="panel-grid">
        <section className="card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Diagnosis</p>
              <h2>Root cause hypotheses</h2>
            </div>
          </div>
          <ul>
            {incident.root_cause_hypotheses.map((item, idx) => (
              <li key={`hypothesis-${idx}`}>{item}</li>
            ))}
          </ul>
        </section>

        <section className="card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Lifecycle</p>
              <h2>Status history</h2>
            </div>
          </div>
          {incident.status_history.length === 0 ? (
            <p className="muted">No lifecycle entries have been recorded yet.</p>
          ) : (
            <ol className="timeline-list status-history-list">
              {incident.status_history.map((entry) => (
                <li key={entry.history_id} className="status-history-item">
                  <div className="status-history-header">
                    <span className={`status-badge status-${entry.status}`}>
                      {statusLabel(entry.status)}
                    </span>
                    <span className="muted">{formatTimestamp(entry.changed_at)}</span>
                  </div>
                  <p className="status-history-copy">
                    {entry.previous_status ? `${statusLabel(entry.previous_status)} -> ` : "Created as "}
                    {statusLabel(entry.status)} by <strong>{entry.actor}</strong>
                  </p>
                  <p className="muted">Source: {entry.source}</p>
                  {entry.reason ? <p className="status-history-reason">{entry.reason}</p> : null}
                </li>
              ))}
            </ol>
          )}
        </section>
      </section>

      <section className="panel-grid">
        <section className="card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Verification</p>
              <h2>Checks and warnings</h2>
            </div>
          </div>
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
          <div className="section-heading">
            <div>
              <p className="eyebrow">Governance</p>
              <h2>Audit trail</h2>
            </div>
          </div>
          {incident.audit_events.length === 0 ? (
            <p className="muted">No audit events have been recorded yet.</p>
          ) : (
            <ul className="audit-log-list">
              {incident.audit_events.map((event) => (
                <li key={event.event_id} className="audit-log-item">
                  <div className="status-history-header">
                    <strong>{event.action.replaceAll(".", " ")}</strong>
                    <span className="muted">{formatTimestamp(event.occurred_at)}</span>
                  </div>
                  <p className="status-history-copy">
                    <strong>{event.actor}</strong> via {event.source}
                  </p>
                  {auditDetailSummary(event.details).length > 0 ? (
                    <ul>
                      {auditDetailSummary(event.details).map((detail) => (
                        <li key={`${event.event_id}-${detail}`}>{detail}</li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      </section>

      <section className="panel-grid">
        <section className="card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Planning</p>
              <h2>Recommended actions</h2>
            </div>
          </div>
          <ul>
            {incident.recommended_actions.map((item, idx) => (
              <li key={`action-${idx}`}>{item}</li>
            ))}
          </ul>
        </section>

        <section className="card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Agent trace</p>
              <h2>Reasoning chain</h2>
            </div>
          </div>
          <ol className="timeline-list">
            {incident.agent_trace.map((item, idx) => (
              <li key={`trace-${idx}`}>{item}</li>
            ))}
          </ol>
        </section>
      </section>

      <section className="card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Evidence</p>
            <h2>Retrieved context</h2>
          </div>
        </div>
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
