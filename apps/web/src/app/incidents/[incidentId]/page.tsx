import Link from "next/link";
import { notFound } from "next/navigation";
import { getIncident, type IncidentReport } from "@/lib/incidents";
import IncidentStatusActions from "@/app/components/incident-status-actions";

function statusLabel(status: IncidentReport["status"]): string {
  const normalized = status.replace("_", " ");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
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
