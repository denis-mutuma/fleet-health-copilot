"""MCP tools for incident operations against the orchestrator API."""

import os
from typing import Any

import httpx

DEFAULT_ORCHESTRATOR_URL = "http://127.0.0.1:8000"


def _orchestrator_base_url() -> str:
    """Resolve orchestrator base URL from env with a safe local default."""
    return os.getenv("ORCHESTRATOR_API_BASE_URL", DEFAULT_ORCHESTRATOR_URL)


def create_incident_from_event(
    event_payload: dict[str, Any], base_url: str = DEFAULT_ORCHESTRATOR_URL
) -> dict[str, Any]:
    """Trigger full orchestration for one telemetry event payload."""
    response = httpx.post(
        f"{base_url.rstrip('/')}/v1/orchestrate/event",
        json=event_payload,
        timeout=10.0
    )
    response.raise_for_status()
    return response.json()


def list_incidents(base_url: str = DEFAULT_ORCHESTRATOR_URL) -> list[dict[str, Any]]:
    """Fetch all incidents from the orchestrator."""
    response = httpx.get(f"{base_url.rstrip('/')}/v1/incidents", timeout=10.0)
    response.raise_for_status()
    return response.json()


def get_incident(
    incident_id: str, base_url: str = DEFAULT_ORCHESTRATOR_URL
) -> dict[str, Any]:
    """Fetch one incident by ID from the orchestrator."""
    response = httpx.get(
        f"{base_url.rstrip('/')}/v1/incidents/{incident_id}",
        timeout=10.0
    )
    response.raise_for_status()
    return response.json()


def update_incident_status(
    incident_id: str,
    status: str,
    base_url: str = DEFAULT_ORCHESTRATOR_URL
) -> dict[str, Any]:
    """Update incident status through the orchestrator API."""
    response = httpx.patch(
        f"{base_url.rstrip('/')}/v1/incidents/{incident_id}",
        json={"status": status},
        timeout=10.0
    )
    response.raise_for_status()
    return response.json()


def get_maintenance_history(
    device_id: str, base_url: str = DEFAULT_ORCHESTRATOR_URL
) -> dict[str, Any]:
    """Provide lightweight maintenance context by filtering incidents for one device."""
    incidents = list_incidents(base_url=base_url)
    return {
        "device_id": device_id,
        "incidents": [
            incident for incident in incidents if incident.get("device_id") == device_id
        ]
    }


def create_mcp_server() -> Any:
    """Create and register MCP tools for incident workflows."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            "The MCP runtime is not installed. Install the mcp-incidents package "
            "with its MCP dependency before starting the server."
        ) from error

    server = FastMCP("fleet-health-incidents")

    @server.tool()
    def create_incident(event_payload: dict[str, Any]) -> dict[str, Any]:
        """Create an incident report from a telemetry event payload."""
        return create_incident_from_event(
            event_payload=event_payload,
            base_url=_orchestrator_base_url(),
        )

    @server.tool()
    def search_incidents() -> list[dict[str, Any]]:
        """List incident reports from the orchestrator."""
        return list_incidents(base_url=_orchestrator_base_url())

    @server.tool()
    def read_incident(incident_id: str) -> dict[str, Any]:
        """Read one incident report from the orchestrator."""
        return get_incident(
            incident_id=incident_id,
            base_url=_orchestrator_base_url(),
        )

    @server.tool()
    def update_incident(incident_id: str, status: str) -> dict[str, Any]:
        """Update an incident status to open, acknowledged, or resolved."""
        return update_incident_status(
            incident_id=incident_id,
            status=status,
            base_url=_orchestrator_base_url(),
        )

    @server.tool()
    def search_maintenance_history(device_id: str) -> dict[str, Any]:
        """List incident history for a device as maintenance context."""
        return get_maintenance_history(
            device_id=device_id,
            base_url=_orchestrator_base_url(),
        )

    return server


def run_server() -> None:
    """Entrypoint used by the package script (`mcp-incidents`)."""
    create_mcp_server().run()


if __name__ == "__main__":
    run_server()
