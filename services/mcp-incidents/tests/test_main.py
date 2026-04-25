import builtins

import pytest

from mcp_incidents import main


class FakeResponse:
    def __init__(self, payload: dict[str, object] | list[dict[str, object]]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object] | list[dict[str, object]]:
        return self.payload


def test_create_incident_from_event_posts_to_orchestrator(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_post(
        url: str,
        json: dict[str, object],
        timeout: float
    ) -> FakeResponse:
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse({"incident_id": "inc_123"})

    monkeypatch.setattr(main.httpx, "post", fake_post)

    result = main.create_incident_from_event(
        event_payload={"event_id": "evt_1"},
        base_url="http://orchestrator:8000/"
    )

    assert calls == [
        {
            "url": "http://orchestrator:8000/v1/orchestrate/event",
            "json": {"event_id": "evt_1"},
            "timeout": 10.0
        }
    ]
    assert result == {"incident_id": "inc_123"}


def test_list_and_get_incidents_call_orchestrator(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, timeout: float) -> FakeResponse:
        calls.append({"url": url, "timeout": timeout})
        if url.endswith("/inc_123"):
            return FakeResponse({"incident_id": "inc_123"})
        return FakeResponse([{"incident_id": "inc_123"}])

    monkeypatch.setattr(main.httpx, "get", fake_get)

    incidents = main.list_incidents(base_url="http://orchestrator:8000/")
    incident = main.get_incident(
        incident_id="inc_123",
        base_url="http://orchestrator:8000/"
    )

    assert calls == [
        {"url": "http://orchestrator:8000/v1/incidents", "timeout": 10.0},
        {"url": "http://orchestrator:8000/v1/incidents/inc_123", "timeout": 10.0}
    ]
    assert incidents == [{"incident_id": "inc_123"}]
    assert incident == {"incident_id": "inc_123"}


def test_create_mcp_server_explains_missing_runtime(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mcp.server.fastmcp":
            raise ImportError("missing mcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="MCP runtime is not installed"):
        main.create_mcp_server()
