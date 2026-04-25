import builtins

import pytest

from mcp_retrieval import main


class FakeResponse:
    def __init__(self, payload: list[dict[str, object]]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict[str, object]]:
        return self.payload


def test_retrieve_supporting_context_calls_orchestrator_search(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object], timeout: float) -> FakeResponse:
        calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(
            [
                {
                    "document_id": "rb_battery_thermal_v2",
                    "source": "runbook",
                    "title": "Battery Thermal Drift Response",
                    "score": 2.0,
                    "excerpt": "Reduce duty cycle."
                }
            ]
        )

    monkeypatch.setattr(main.httpx, "get", fake_get)

    result = main.retrieve_supporting_context(
        query="battery thermal",
        base_url="http://orchestrator:8000/",
        limit=3
    )

    assert calls == [
        {
            "url": "http://orchestrator:8000/v1/rag/search",
            "params": {"query": "battery thermal", "limit": 3},
            "timeout": 10.0
        }
    ]
    assert result["query"] == "battery thermal"
    assert result["hits"][0]["document_id"] == "rb_battery_thermal_v2"


def test_create_mcp_server_explains_missing_runtime(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mcp.server.fastmcp":
            raise ImportError("missing mcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="MCP runtime is not installed"):
        main.create_mcp_server()
