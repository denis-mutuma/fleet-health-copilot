import builtins

import httpx
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


def test_update_incident_status_calls_orchestrator(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_patch(
        url: str,
        json: dict[str, object],
        timeout: float
    ) -> FakeResponse:
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse({"incident_id": "inc_123", "status": "resolved"})

    monkeypatch.setattr(main.httpx, "patch", fake_patch)

    result = main.update_incident_status(
        incident_id="inc_123",
        status="resolved",
        base_url="http://orchestrator:8000/"
    )

    assert calls == [
        {
            "url": "http://orchestrator:8000/v1/incidents/inc_123",
            "json": {"status": "resolved"},
            "timeout": 10.0
        }
    ]
    assert result == {"incident_id": "inc_123", "status": "resolved"}


def test_get_maintenance_history_filters_incidents(monkeypatch) -> None:
    def fake_get(url: str, timeout: float) -> FakeResponse:
        return FakeResponse(
            [
                {"incident_id": "inc_1", "device_id": "robot-03"},
                {"incident_id": "inc_2", "device_id": "robot-07"}
            ]
        )

    monkeypatch.setattr(main.httpx, "get", fake_get)

    result = main.get_maintenance_history(device_id="robot-03")

    assert result == {
        "device_id": "robot-03",
        "incidents": [{"incident_id": "inc_1", "device_id": "robot-03"}]
    }


def test_create_mcp_server_explains_missing_runtime(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mcp.server.fastmcp":
            raise ImportError("missing mcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="MCP runtime is not installed"):
        main.create_mcp_server()


def test_list_incidents_surfaces_timeout_with_operation_context(monkeypatch) -> None:
    def fake_get(url: str, timeout: float) -> FakeResponse:
        request = httpx.Request("GET", url)
        raise httpx.TimeoutException("timed out", request=request)

    monkeypatch.setattr(main.httpx, "get", fake_get)

    with pytest.raises(RuntimeError, match="list_incidents request to .* timed out"):
        main.list_incidents(base_url="http://orchestrator:8000/")


def test_get_incident_surfaces_http_status_with_backend_detail(monkeypatch) -> None:
    class ErrorResponse:
        status_code = 404

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "detail": "Incident not found.",
                "error": {"code": "resource_not_found", "message": "Incident not found."},
            }

        def raise_for_status(self) -> None:
            request = httpx.Request("GET", "http://orchestrator:8000/v1/incidents/inc_missing")
            raise httpx.HTTPStatusError("not found", request=request, response=self)

    def fake_get(url: str, timeout: float) -> ErrorResponse:
        _ = timeout
        assert url.endswith("/inc_missing")
        return ErrorResponse()

    monkeypatch.setattr(main.httpx, "get", fake_get)

    with pytest.raises(RuntimeError, match="get_incident request to .* failed with HTTP 404: Incident not found"):
        main.get_incident(incident_id="inc_missing", base_url="http://orchestrator:8000/")
