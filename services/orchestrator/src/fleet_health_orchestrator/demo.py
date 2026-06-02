"""AWS Lambda demo helpers for a zero-bill, ephemeral deployment path."""

from __future__ import annotations

from datetime import datetime, timezone

from fleet_health_orchestrator.dependencies import AppDependencies
from fleet_health_orchestrator.models import TelemetryEvent


DEMO_RUNBOOKS = [
    {
        "document_id": "rb_battery_thermal_demo",
        "source": "runbook",
        "title": "Battery Thermal Containment",
        "content": (
            "When battery_temp_c exceeds threshold, reduce drive duty cycle, "
            "increase cooling, inspect intake and exhaust paths, and remove the "
            "robot from service if temperature does not trend down within 10 minutes."
        ),
        "tags": ["battery", "thermal", "safety"],
    },
    {
        "document_id": "rb_motor_current_demo",
        "source": "runbook",
        "title": "Motor Current Fault Isolation",
        "content": (
            "When motor_current_a remains above threshold, cap acceleration, inspect "
            "payload mass, check wheel drag and gearbox friction, then validate motor "
            "harness connectors and phase balance."
        ),
        "tags": ["motor", "current", "mechanical"],
    },
]

DEMO_EVENT = TelemetryEvent(
    event_id="evt_lambda_demo_thermal",
    fleet_id="fleet-demo",
    device_id="robot-03",
    timestamp=datetime(2026, 4, 27, 8, 2, tzinfo=timezone.utc),
    metric="battery_temp_c",
    value=71.8,
    threshold=65.0,
    severity="high",
    tags=["battery", "thermal"],
)


def seed_lambda_demo_state(dependencies: AppDependencies) -> None:
    """Seed a tiny demo corpus and incident into ephemeral Lambda storage."""
    if dependencies.repository.list_rag_documents():
        return

    for document in DEMO_RUNBOOKS:
        dependencies.repository.insert_rag_document(
            document_id=str(document["document_id"]),
            source=str(document["source"]),
            title=str(document["title"]),
            content=str(document["content"]),
            tags=list(document["tags"]),
        )

    dependencies.repository.insert_event(DEMO_EVENT)
    incident = dependencies.orchestrator.execute(
        event=DEMO_EVENT,
        rag_documents=dependencies.repository.list_rag_documents(),
    )
    dependencies.repository.insert_incident(incident)
    dependencies.logger.info("Seeded Lambda demo state with sample runbooks and incident.")
