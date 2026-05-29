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

function priorityLabel(incident: IncidentReport): string {
  if (incident.status === "open" && incident.verification.passed === false) {
    return "High priority";
  }
  if (incident.status === "open" || incident.confidence_score >= 0.8) {
    return "Needs review";
  }
  return "Stable";
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
  const backendStatus = orchestratorUnavailable ? "Backend offline" : "Backend connected";

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
          <p className="eyebrow">Fleet operations</p>
        </div>
        <h1>Fleet Health Copilot</h1>
        <p className="hero-copy">
          One place to inspect incidents, review grounded diagnoses, keep retrieval current, and
          move from signal to action without leaving the console.
        </p>
      </header>

      <section
        className={`status-banner ${orchestratorUnavailable ? "status-banner-offline" : ""}`}
        aria-live="polite"
      >
        <strong>{backendStatus}</strong>
        <span>
          {orchestratorUnavailable
            ? "Start the orchestrator on port 8000 to load incidents and actions."
            : "Incident data and grounded actions are available."}
        </span>
      </section>

      <section className="ops-kpi-grid" aria-label="Incident status summary">
        <div className="stat-card">
          <span className="stat-value">{incidentCounts.open}</span>
          <span className="stat-label">Open</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{incidentCounts.acknowledged}</span>
          <span className="stat-label">Acknowledged</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{incidentCounts.resolved}</span>
          <span className="stat-label">Resolved</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{incidents.length}</span>
          <span className="stat-label">Total records</span>
        </div>
      </section>

      <section className="ops-dashboard-grid">
        <section className="card ops-queue-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Incident queue</p>
              <h2>Active operational picture</h2>
            </div>
            <span className="muted">{incidents.length} records</span>
          </div>

          {orchestratorUnavailable ? (
            <p className="error">
              Orchestrator is unavailable. Start the API on port 8000, then refresh this page.
            </p>
          ) : incidents.length === 0 ? (
            <p className="muted">No incidents yet. Trigger a simulation to populate the dashboard.</p>
          ) : (
            <ul className="ops-incident-list">
              {incidents.map((incident) => (
                <li key={incident.incident_id}>
                  <Link href={`/incidents/${incident.incident_id}`} className="ops-incident-row">
                    <span>
                      <strong>{incident.device_id}</strong>
                      <span className="incident-summary">{incident.summary}</span>
                    </span>
                    <span className="ops-incident-meta">
                      <span className={`status-badge status-${incident.status}`}>
                        {statusLabel(incident.status)}
                      </span>
                      <span>{priorityLabel(incident)}</span>
                      <span>{(incident.confidence_score * 100).toFixed(0)}% confidence</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <aside className="card ops-action-rail" aria-label="Operator actions">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Actions</p>
              <h2>Next move</h2>
            </div>
          </div>
          <SimulateIncidentButton />
          <Link href={reviewIncidentsHref} className="secondary-button rag-link-button">
            Review latest incident
          </Link>
          <Link href="/chat" className="secondary-button rag-link-button">
            Open operator chat
          </Link>
          <Link href="/rag" className="secondary-button rag-link-button">
            Manage knowledge
          </Link>
          <div className="ops-rail-note">
            <strong>Grounding status</strong>
            <span>Chat answers use the indexed corpus and incident records when available.</span>
          </div>
        </aside>
      </section>

      <section className="panel-grid">
        <RagUploadForm />
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
    </main>
  );
}
