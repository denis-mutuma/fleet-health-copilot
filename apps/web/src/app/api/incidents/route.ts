import { NextResponse } from "next/server";
import { listIncidents, orchestrateCanonicalEvent } from "@/lib/incidents";

export async function GET() {
  try {
    const incidents = await listIncidents();
    return NextResponse.json(incidents);
  } catch {
    return NextResponse.json(
      { error: "Orchestrator is unavailable." },
      { status: 502 }
    );
  }
}

export async function POST() {
  try {
    const incident = await orchestrateCanonicalEvent();
    return NextResponse.json(incident, { status: 201 });
  } catch {
    return NextResponse.json(
      { error: "Could not orchestrate event." },
      { status: 502 }
    );
  }
}
