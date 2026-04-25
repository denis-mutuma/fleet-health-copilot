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
        <IncidentStatusActions
          incidentId={incident.incident_id}
          status={incident.status}
        />
        <p>
          <Link href="/">Back to dashboard</Link>
        </p>
      </header>

      <section className="card">
        <h2>Root cause hypotheses</h2>
        <ul>
          {incident.root_cause_hypotheses.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Recommended actions</h2>
        <ul>
          {incident.recommended_actions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Evidence</h2>
        {Object.entries(incident.evidence).map(([key, values]) => (
          <div key={key} className="evidence-group">
            <h3>{key}</h3>
            <ul>
              {values.map((value) => (
                <li key={value}>{value}</li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    </main>
  );
}
