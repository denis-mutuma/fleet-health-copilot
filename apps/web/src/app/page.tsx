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

function verificationLabel(incident: IncidentReport): string {
  if (incident.verification.passed === false) {
    return "Flagged";
  }
  if ((incident.verification.warnings ?? []).length > 0) {
    return "Review";
  }
  return "Passed";
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
  const latestIncident = incidents[0];

  return (
    <main className="container home-layout" aria-label="Fleet incident operations board">
      <header className="command-header">
        <div className="command-lockup">
          <Image
            src="/logo.png"
            alt="Fleet Health Copilot logo"
            className="brand-logo"
            width={28}
            height={28}
          />
          <div>
            <p className="eyebrow">Fleet command</p>
            <h1>Operations board</h1>
          </div>
        </div>
        <div className="command-meta" aria-label="Current operating context">
          <span className={orchestratorUnavailable ? "state-danger" : "state-ok"}>{backendStatus}</span>
          <span>{latestIncident ? `Last signal ${latestIncident.device_id}` : "No active signal"}</span>
          <span>{incidents.length} incident records</span>
        </div>
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

      <section className="telemetry-strip" aria-label="Incident status summary">
        <div className="telemetry-cell telemetry-alert">
          <span className="telemetry-label">Open</span>
          <span className="telemetry-value">{incidentCounts.open}</span>
        </div>
        <div className="telemetry-cell telemetry-review">
          <span className="telemetry-label">Acknowledged</span>
          <span className="telemetry-value">{incidentCounts.acknowledged}</span>
        </div>
        <div className="telemetry-cell telemetry-ok">
          <span className="telemetry-label">Resolved</span>
          <span className="telemetry-value">{incidentCounts.resolved}</span>
        </div>
        <div className="telemetry-cell">
          <span className="telemetry-label">Corpus</span>
          <span className="telemetry-value">Linked</span>
        </div>
        <div className="telemetry-cell">
          <span className="telemetry-label">Backend</span>
          <span className="telemetry-value">{orchestratorUnavailable ? "Offline" : "Online"}</span>
        </div>
      </section>

      <section className="ops-dashboard-grid">
        <section className="card ops-queue-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Incident queue</p>
              <h2>Active signals</h2>
            </div>
            <span className="muted">{incidents.length} records</span>
          </div>

          {orchestratorUnavailable ? (
            <p className="error">
              Orchestrator is unavailable. Start the API on port 8000, then refresh this page.
            </p>
          ) : incidents.length === 0 ? (
            <p className="muted">No incidents are loaded. Trigger a simulation to populate the board.</p>
          ) : (
            <div className="ops-table" role="table" aria-label="Incident queue">
              <div className="ops-table-head" role="row">
                <span>Device</span>
                <span>Incident</span>
                <span>Status</span>
                <span>Priority</span>
                <span>Confidence</span>
                <span>Verify</span>
              </div>
              {incidents.map((incident) => (
                <Link
                  key={incident.incident_id}
                  href={`/incidents/${incident.incident_id}`}
                  className="ops-table-row"
                  role="row"
                >
                  <span className="ops-table-device mono">{incident.device_id}</span>
                  <span className="ops-table-summary">
                    <strong className="mono">{incident.incident_id}</strong>
                    <span>{incident.summary}</span>
                  </span>
                  <span>
                    <span className={`status-badge status-${incident.status}`}>
                      {statusLabel(incident.status)}
                    </span>
                  </span>
                  <span>{priorityLabel(incident)}</span>
                  <span>{(incident.confidence_score * 100).toFixed(0)}%</span>
                  <span>{verificationLabel(incident)}</span>
                </Link>
              ))}
            </div>
          )}
        </section>

        <aside className="card ops-action-rail" aria-label="Operator actions">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Dispatch</p>
              <h2>Operator actions</h2>
            </div>
          </div>
          <SimulateIncidentButton />
          <Link href={reviewIncidentsHref} className="secondary-button rag-link-button">
            Open latest report
          </Link>
          <Link href="/chat" className="secondary-button rag-link-button">
            Open comms channel
          </Link>
          <Link href="/rag" className="secondary-button rag-link-button">
            Check corpus inventory
          </Link>
          <div className="ops-rail-note">
            <strong>Runbook readiness</strong>
            <span>Chat uses indexed runbooks and incident records when the backend is online.</span>
          </div>
        </aside>
      </section>

      <section className="panel-grid">
        <RagUploadForm />
        <section className="card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Run sequence</p>
              <h2>Standard triage loop</h2>
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
