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

export default async function HomePage() {
  let incidents: IncidentReport[] = [];
  let orchestratorUnavailable = false;

  try {
    incidents = await listIncidents();
  } catch {
    orchestratorUnavailable = true;
  }

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

      <section className="card">
        <h2>Active incidents</h2>
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
                  <strong>{incident.incident_id}</strong> · {incident.device_id}{" "}
                  · {incident.status.toUpperCase()} — {incident.summary}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
