"""MCP tools for telemetry and quick device health lookups."""

import os
from typing import Any

import httpx

DEFAULT_ORCHESTRATOR_URL = "http://127.0.0.1:8000"


def _response_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except Exception:
        return None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return None


def _request_json(
    *,
    operation: str,
    request_fn: Any,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    try:
        response = request_fn(url, **kwargs)
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"{operation} request to {url} timed out") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"{operation} request to {url} failed: {exc}") from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _response_error_detail(response)
        message = f"{operation} request to {url} failed with HTTP {response.status_code}"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message) from exc
    return response


def _orchestrator_base_url() -> str:
    """Resolve orchestrator base URL from env with a safe local default."""
    return os.getenv("ORCHESTRATOR_API_BASE_URL", DEFAULT_ORCHESTRATOR_URL)


def query_latest_events(
    device_id: str, base_url: str = DEFAULT_ORCHESTRATOR_URL, limit: int = 20
) -> dict[str, Any]:
    """Return recent events for one device from the orchestrator event stream."""
    response = _request_json(
        operation="query_latest_events",
        request_fn=httpx.get,
        url=f"{base_url.rstrip('/')}/v1/events",
        timeout=10.0,
    )
    events = response.json()
    # MCP tool contracts are device-centric, so filter server response in-process.
    filtered = [event for event in events if event["device_id"] == device_id][:limit]
    return {"device_id": device_id, "events": filtered}


def lookup_device_status(
    device_id: str, base_url: str = DEFAULT_ORCHESTRATOR_URL
) -> dict[str, Any]:
    """Compute a simple nominal/anomalous health snapshot from the latest event."""
    events = query_latest_events(device_id=device_id, base_url=base_url, limit=1)["events"]
    if not events:
        return {"device_id": device_id, "status": "unknown", "latest_event": None}

    latest_event = events[0]
    is_anomalous = latest_event["value"] > latest_event["threshold"]
    return {
        "device_id": device_id,
        "status": "anomalous" if is_anomalous else "nominal",
        "latest_event": latest_event
    }


def create_mcp_server() -> Any:
    """Create and register MCP tools for telemetry workflows."""
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
            base_url=_orchestrator_base_url(),
            limit=limit
        )

    @server.tool()
    def lookup_device_health(device_id: str) -> dict[str, Any]:
        """Return a simple device health status from the latest telemetry event."""
        return lookup_device_status(
            device_id=device_id,
            base_url=_orchestrator_base_url()
        )

    return server


def run_server() -> None:
    """Entrypoint used by the package script (`mcp-telemetry`)."""
    create_mcp_server().run()


if __name__ == "__main__":
    run_server()
