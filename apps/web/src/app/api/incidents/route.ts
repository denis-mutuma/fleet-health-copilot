import { NextResponse } from "next/server";
import { apiErrorPayload, toApiError } from "@/lib/api";
import { listIncidents, orchestrateCanonicalEvent } from "@/lib/incidents";

export async function GET() {
  try {
    const incidents = await listIncidents();
    return NextResponse.json(incidents);
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(
      apiErrorPayload(apiError.message, "upstream_request_failed"),
      { status: apiError.status }
    );
  }
}

export async function POST() {
  try {
    const incident = await orchestrateCanonicalEvent();
    return NextResponse.json(incident, { status: 201 });
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(
      apiErrorPayload(apiError.message, "upstream_request_failed"),
      { status: apiError.status }
    );
  }
}
