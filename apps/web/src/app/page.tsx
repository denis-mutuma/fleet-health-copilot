import Image from "next/image";
import Link from "next/link";
import {
  SignInButton,
  SignedIn,
  SignedOut,
  UserButton
} from "@clerk/nextjs";
import SimulateIncidentButton from "./components/simulate-incident-button";
import { listIncidents, type IncidentReport } from "@/lib/incidents";

function statusLabel(status: IncidentReport["status"]): string {
  return status.replace("_", " ").toUpperCase();
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
    <main className="container">
      <header className="hero">
        <div className="header-row">
          <div className="brand-row">
            <Image
              src="/logo.png"
              alt="Fleet Health Copilot logo"
              className="brand-logo"
              width={28}
              height={28}
            />
            <p className="eyebrow">Fleet Health Copilot</p>
          </div>
          <div>
            <SignedIn>
              <UserButton />
            </SignedIn>
            <SignedOut>
              <SignInButton mode="modal" />
            </SignedOut>
          </div>
        </div>
        <h1>Incident Operations Dashboard</h1>
        <p>
          MVP view for authenticated operators. Live ingestion, multi-agent
          reasoning, and report generation are provided by the orchestrator.
        </p>
        <SimulateIncidentButton />
      </header>

      <section className="stats-grid" aria-label="Incident status summary">
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
      </section>

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
            Orchestrator is unavailable. Start the API on port 8000, then
            refresh this page.
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
                  <span>
                    <strong>{incident.incident_id}</strong>
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
    </main>
  );
}
