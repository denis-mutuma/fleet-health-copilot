import builtins

import pytest

from mcp_telemetry import main


class FakeResponse:
    def __init__(self, payload: list[dict[str, object]]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict[str, object]]:
        return self.payload


def test_query_latest_events_filters_device_and_strips_base_url(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, timeout: float) -> FakeResponse:
        calls.append({"url": url, "timeout": timeout})
        return FakeResponse(
            [
                {"event_id": "evt_1", "device_id": "robot-03"},
                {"event_id": "evt_2", "device_id": "robot-07"},
                {"event_id": "evt_3", "device_id": "robot-03"}
            ]
        )

    monkeypatch.setattr(main.httpx, "get", fake_get)

    result = main.query_latest_events(
        device_id="robot-03",
        base_url="http://orchestrator:8000/",
        limit=1
    )

    assert calls == [{"url": "http://orchestrator:8000/v1/events", "timeout": 10.0}]
    assert result == {
        "device_id": "robot-03",
        "events": [{"event_id": "evt_1", "device_id": "robot-03"}]
    }


def test_lookup_device_status_reports_latest_health(monkeypatch) -> None:
    def fake_get(url: str, timeout: float) -> FakeResponse:
        return FakeResponse(
            [
                {
                    "event_id": "evt_1",
                    "device_id": "robot-03",
                    "value": 80.0,
                    "threshold": 65.0
                }
            ]
        )

    monkeypatch.setattr(main.httpx, "get", fake_get)

    result = main.lookup_device_status(device_id="robot-03")

    assert result["status"] == "anomalous"
    assert result["latest_event"] == {
        "event_id": "evt_1",
        "device_id": "robot-03",
        "value": 80.0,
        "threshold": 65.0
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
