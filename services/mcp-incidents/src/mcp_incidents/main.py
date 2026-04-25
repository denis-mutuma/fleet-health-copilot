import os
from typing import Any

import httpx

DEFAULT_ORCHESTRATOR_URL = "http://127.0.0.1:8000"


def create_incident_from_event(
    event_payload: dict[str, Any], base_url: str = DEFAULT_ORCHESTRATOR_URL
) -> dict[str, Any]:
    response = httpx.post(
        f"{base_url.rstrip('/')}/v1/orchestrate/event",
        json=event_payload,
        timeout=10.0
    )
    response.raise_for_status()
    return response.json()


def list_incidents(base_url: str = DEFAULT_ORCHESTRATOR_URL) -> list[dict[str, Any]]:
    response = httpx.get(f"{base_url.rstrip('/')}/v1/incidents", timeout=10.0)
    response.raise_for_status()
    return response.json()


def get_incident(
    incident_id: str, base_url: str = DEFAULT_ORCHESTRATOR_URL
) -> dict[str, Any]:
    response = httpx.get(
        f"{base_url.rstrip('/')}/v1/incidents/{incident_id}",
        timeout=10.0
    )
    response.raise_for_status()
    return response.json()


def create_mcp_server() -> Any:
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
            base_url=os.getenv("ORCHESTRATOR_API_BASE_URL", DEFAULT_ORCHESTRATOR_URL)
        )

    @server.tool()
    def search_incidents() -> list[dict[str, Any]]:
        """List incident reports from the orchestrator."""
        return list_incidents(
            base_url=os.getenv("ORCHESTRATOR_API_BASE_URL", DEFAULT_ORCHESTRATOR_URL)
        )

    @server.tool()
    def read_incident(incident_id: str) -> dict[str, Any]:
        """Read one incident report from the orchestrator."""
        return get_incident(
            incident_id=incident_id,
            base_url=os.getenv("ORCHESTRATOR_API_BASE_URL", DEFAULT_ORCHESTRATOR_URL)
        )

    return server


def run_server() -> None:
    create_mcp_server().run()


if __name__ == "__main__":
    run_server()
