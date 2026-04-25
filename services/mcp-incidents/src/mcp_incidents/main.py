from typing import Any

import httpx


def create_incident_from_event(
    event_payload: dict[str, Any], base_url: str = "http://127.0.0.1:8000"
) -> dict[str, Any]:
    response = httpx.post(
        f"{base_url}/v1/orchestrate/event",
        json=event_payload,
        timeout=10.0
    )
    response.raise_for_status()
    return response.json()


def list_incidents(base_url: str = "http://127.0.0.1:8000") -> list[dict[str, Any]]:
    response = httpx.get(f"{base_url}/v1/incidents", timeout=10.0)
    response.raise_for_status()
    return response.json()
