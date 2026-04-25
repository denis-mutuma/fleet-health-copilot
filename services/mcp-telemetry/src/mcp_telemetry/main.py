from typing import Any

import httpx


def query_latest_events(
    device_id: str, base_url: str = "http://127.0.0.1:8000", limit: int = 20
) -> dict[str, Any]:
    response = httpx.get(f"{base_url}/v1/events", timeout=10.0)
    response.raise_for_status()
    events = response.json()
    filtered = [event for event in events if event["device_id"] == device_id][:limit]
    return {"device_id": device_id, "events": filtered}
