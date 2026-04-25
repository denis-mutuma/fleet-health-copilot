import os
from typing import Any

import httpx

DEFAULT_ORCHESTRATOR_URL = "http://127.0.0.1:8000"


def query_latest_events(
    device_id: str, base_url: str = DEFAULT_ORCHESTRATOR_URL, limit: int = 20
) -> dict[str, Any]:
    response = httpx.get(f"{base_url.rstrip('/')}/v1/events", timeout=10.0)
    response.raise_for_status()
    events = response.json()
    filtered = [event for event in events if event["device_id"] == device_id][:limit]
    return {"device_id": device_id, "events": filtered}


def create_mcp_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            "The MCP runtime is not installed. Install the mcp-telemetry package "
            "with its MCP dependency before starting the server."
        ) from error

    server = FastMCP("fleet-health-telemetry")

    @server.tool()
    def query_device_events(device_id: str, limit: int = 20) -> dict[str, Any]:
        """Query recent telemetry events for a device through the orchestrator API."""
        return query_latest_events(
            device_id=device_id,
            base_url=os.getenv("ORCHESTRATOR_API_BASE_URL", DEFAULT_ORCHESTRATOR_URL),
            limit=limit
        )

    return server


def run_server() -> None:
    create_mcp_server().run()


if __name__ == "__main__":
    run_server()
