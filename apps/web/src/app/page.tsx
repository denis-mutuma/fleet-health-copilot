import Image from "next/image";
import Link from "next/link";
import SimulateIncidentButton from "./components/simulate-incident-button";
import RagUploadForm from "./components/rag-upload-form";
import { listIncidents, type IncidentReport } from "@/lib/incidents";

function statusLabel(status: IncidentReport["status"]): string {
  const normalized = status.replace("_", " ");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export default async function HomePage() {
  let incidents: IncidentReport[] = [];
  let orchestratorUnavailable = false;

  try {
    incidents = await listIncidents();
  } catch {
    orchestratorUnavailable = true;
  }

  const incidentCounts = incidents.reduce(
    (counts, incident) => {
      counts[incident.status] += 1;
      return counts;
    },
    { open: 0, acknowledged: 0, resolved: 0 }
  );

  return (
    <main className="container page-grid" aria-label="Fleet incident operations dashboard">
      <header className="hero">
        <div className="brand-row">
          <Image
            src="/logo.png"
            alt="Fleet Health Copilot logo"
            className="brand-logo"
            width={28}
            height={28}
          />
          <p className="eyebrow">Operator console</p>
        </div>
        <h1>Run fleet incidents from one grounded workspace.</h1>
        <p>
          Monitor active reports, inspect evidence-backed diagnoses, escalate through chat,
          and manage retrieval context without leaving the console.
        </p>
        <div className="report-metadata">
          <span>{incidents.length} incident records</span>
          <span>6-agent orchestration</span>
          <span>Retrieval-backed reasoning</span>
        </div>
        <div className="actions action-group">
          <Link href="/chat" className="secondary-button rag-link-button">
            Open operator chat
          </Link>
          <Link href="/rag" className="secondary-button rag-link-button">
            Manage knowledge corpus
          </Link>
        </div>
        <SimulateIncidentButton />
      </header>

      <section className="stats-grid" aria-label="Incident status summary">
        <div className="stat-card">
          <span className="stat-value">{incidentCounts.open}</span>
          <span className="stat-label">Open incidents</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{incidentCounts.acknowledged}</span>
          <span className="stat-label">Acknowledged</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{incidentCounts.resolved}</span>
          <span className="stat-label">Resolved</span>
        </div>
      </section>

      <section className="panel-grid">
        <section className="card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Operations queue</p>
              <h2>Latest incidents</h2>
            </div>
            <span className="muted">{incidents.length} total</span>
          </div>
          {orchestratorUnavailable ? (
            <p className="error">
              Orchestrator is unavailable. Start the API on port 8000, then refresh this page.
            </p>
          ) : incidents.length === 0 ? (
            <p className="muted">
              No incidents yet. Trigger a simulation to populate the dashboard.
            </p>
          ) : (
            <ul className="incident-list">
              {incidents.map((incident) => (
                <li key={incident.incident_id} className="incident-list-item">
                  <Link href={`/incidents/${incident.incident_id}`}>
                    <span className="chat-incident-header">
                      <strong className="mono">{incident.incident_id}</strong>
                      <span className={`status-badge status-${incident.status}`}>
                        {statusLabel(incident.status)}
                      </span>
                    </span>
                    <span className="incident-summary">
                      {incident.device_id} · {incident.summary}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="stack-grid">
          <section className="card">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Operator flow</p>
                <h2>Suggested loop</h2>
              </div>
            </div>
            <ol className="timeline-list">
              <li>Trigger or ingest an incident and confirm the queue updates.</li>
              <li>Open the incident to inspect evidence, hypotheses, and verification.</li>
              <li>Jump into chat for follow-up actions, status changes, and grounded Q&A.</li>
            </ol>
          </section>

          <RagUploadForm />
        </div>
      </section>
    </main>
  );
}
