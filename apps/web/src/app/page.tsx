import Image from "next/image";
import Link from "next/link";
import SimulateIncidentButton from "./components/simulate-incident-button";
import RagUploadForm from "./components/rag-upload-form";
import { listIncidents, type IncidentReport } from "@/lib/incidents";

export const dynamic = "force-dynamic";

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
  const reviewIncidentsHref = incidents[0]
    ? `/incidents/${incidents[0].incident_id}`
    : "/chat";

  return (
    <main className="container home-layout" aria-label="Fleet incident operations dashboard">
      <header className="hero hero-home">
        <div className="brand-row">
          <Image
            src="/logo.png"
            alt="Fleet Health Copilot logo"
            className="brand-logo"
            width={28}
            height={28}
          />
          <p className="eyebrow">Codex-style workspace</p>
        </div>
        <h1>Fleet Health Copilot</h1>
        <p className="hero-copy">
          One place to inspect incidents, review grounded diagnoses, keep retrieval current, and
          move from signal to action without leaving the console.
        </p>
        <div className="report-metadata">
          <span>{incidents.length} incident records</span>
          <span>{incidentCounts.open} open</span>
          <span>{incidentCounts.resolved} resolved</span>
          <span>Retrieval-backed reasoning</span>
        </div>
        <div className="actions action-group">
          <Link href="/chat" className="button rag-link-button">
            Open chat
          </Link>
          <Link href={reviewIncidentsHref} className="secondary-button rag-link-button">
            Review incidents
          </Link>
          <Link href="/rag" className="secondary-button rag-link-button">
            Manage knowledge
          </Link>
        </div>
        <div className="hero-tools">
          <SimulateIncidentButton />
        </div>
      </header>

      <section className="showcase-grid" aria-label="Workspace overview">
        <section className="showcase-panel showcase-panel-wide">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Workspace</p>
              <h2>Operator overview</h2>
            </div>
            <span className="muted">{orchestratorUnavailable ? "Backend offline" : "Backend connected"}</span>
          </div>

          <div className="workspace-mock">
            <div className="workspace-column">
              <p className="workspace-label">Primary navigation</p>
              <ul className="workspace-nav-list">
                <li>Operations dashboard</li>
                <li>Operator chat</li>
                <li>Knowledge corpus</li>
              </ul>
            </div>

            <div className="workspace-column workspace-column-main">
              <div className="workspace-card">
                <div className="section-heading compact">
                  <div>
                    <p className="eyebrow">Queue</p>
                    <h3>Latest incidents</h3>
                  </div>
                  <span className="muted">{incidents.length} total</span>
                </div>
                {orchestratorUnavailable ? (
                  <p className="error">
                    Orchestrator is unavailable. Start the API on port 8000, then refresh the page.
                  </p>
                ) : incidents.length === 0 ? (
                  <p className="muted">No incidents yet. Simulate one to populate the queue.</p>
                ) : (
                  <ul className="incident-list compact-list">
                    {incidents.slice(0, 3).map((incident) => (
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
              </div>

              <div className="workspace-grid">
                <div className="workspace-card">
                  <p className="workspace-label">Chat</p>
                  <h3>Ask for a diagnosis, checklist, or report draft.</h3>
                  <p className="muted">
                    Use the operator chat to review evidence, reason over incidents, and coordinate
                    follow-up steps.
                  </p>
                </div>
                <div className="workspace-card">
                  <p className="workspace-label">Knowledge</p>
                  <h3>Keep runbooks current.</h3>
                  <p className="muted">
                    Upload source documents so retrieval stays grounded when the copilot answers.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="stack-grid">
          <section className="card">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Status</p>
                <h2>Incident counts</h2>
              </div>
            </div>
            <div className="stats-grid">
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
            </div>
          </section>

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
              <li>Jump into chat for follow-up actions, status changes, and grounded Q&amp;A.</li>
            </ol>
          </section>
        </section>
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
            <p className="muted">No incidents yet. Trigger a simulation to populate the dashboard.</p>
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
          <RagUploadForm />
        </div>
      </section>
    </main>
  );
}
