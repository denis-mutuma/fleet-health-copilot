from types import SimpleNamespace
import time

import httpx

from fleet_health_orchestrator.chat_orchestrator import ChatToolOrchestrator
from fleet_health_orchestrator.mcp_client_adapter import MCPClientAdapter


class _FakeRepo:
    def list_rag_documents(self):
        return [
            {
                "document_id": "rb_battery_thermal_v2",
                "source": "runbook",
                "title": "Battery Thermal Drift Response",
                "content": "Reduce duty cycle and inspect cooling.",
                "tags": ["battery", "thermal"],
            }
        ]

    def list_incidents(self):
        return []

    def get_incident(self, _incident_id: str):
        return None

    def update_incident_status(self, _incident_id: str, _status: str):
        return None

    def list_events(self):
        return []


class _FakeRetrievalBackend:
    def search(self, query: str, documents: list[dict[str, object]], limit: int = 5):
        assert query
        assert documents
        assert limit > 0
        return [
            SimpleNamespace(
                document_id="rb_battery_thermal_v2",
                source="runbook",
                title="Battery Thermal Drift Response",
                score=0.91,
                excerpt="Reduce duty cycle and inspect cooling.",
            )
        ]


def test_mcp_adapter_search_operational_context_returns_hits() -> None:
    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=_FakeRetrievalBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )

    result = adapter.call_tool(
        "search_operational_context",
        {"query": "battery thermal drift", "limit": 3},
    )

    assert result.error is None
    assert result.output["query"] == "battery thermal drift"
    assert len(result.output["hits"]) == 1
    assert result.output["hits"][0]["document_id"] == "rb_battery_thermal_v2"


def test_chat_orchestrator_returns_none_when_llm_disabled() -> None:
    settings = SimpleNamespace(
        llm_chat_enabled=False,
        openai_api_key="",
        llm_chat_model="gpt-4o-mini",
        llm_chat_temperature=0.2,
        llm_chat_max_output_tokens=400,
        chat_tool_max_calls_per_turn=4,
    )

    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=_FakeRetrievalBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )
    orchestrator = ChatToolOrchestrator(
        logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
        settings=settings,
        mcp_adapter=adapter,
    )

    result = orchestrator.run_turn(
        user_content="What runbook should I use for battery thermal drift?",
        session=SimpleNamespace(session_id="chat_1", incident_id=None),
        chat_history=[],
    )

    assert result is None


def test_chat_orchestrator_generates_content_without_tool_calls(monkeypatch) -> None:
    class FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="Use the battery thermal runbook.", tool_calls=[])
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=8, total_tokens=18),
            )

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, api_key: str):
            assert api_key == "sk-test"
            self.chat = FakeChat()

    monkeypatch.setattr("fleet_health_orchestrator.chat_orchestrator.OpenAI", FakeOpenAI)

    settings = SimpleNamespace(
        llm_chat_enabled=True,
        openai_api_key="sk-test",
        llm_chat_model="gpt-4o-mini",
        llm_chat_temperature=0.2,
        llm_chat_max_output_tokens=400,
        chat_tool_max_calls_per_turn=4,
        llm_chat_input_cost_per_1k_tokens_usd=0.01,
        llm_chat_output_cost_per_1k_tokens_usd=0.03,
    )

    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=_FakeRetrievalBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )
    orchestrator = ChatToolOrchestrator(
        logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
        settings=settings,
        mcp_adapter=adapter,
    )

    result = orchestrator.run_turn(
        user_content="What runbook should I use for battery thermal drift?",
        session=SimpleNamespace(session_id="chat_1", incident_id=None),
        chat_history=[],
    )

    assert result is not None
    assert result.content == "Use the battery thermal runbook."
    assert result.action == "rag_answer"
    assert result.action_status == "success"
    assert result.llm_cost_usd == 0.00034


def test_chat_orchestrator_enforces_tool_limit_with_multiple_calls_in_one_response(monkeypatch) -> None:
    class FakeCompletions:
        call_count = 0

        @classmethod
        def create(cls, **_kwargs):
            cls.call_count += 1
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="tool_1",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="search_operational_context",
                                        arguments='{"query":"battery thermal drift"}',
                                    ),
                                ),
                                SimpleNamespace(
                                    id="tool_2",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="search_operational_context",
                                        arguments='{"query":"battery cooling"}',
                                    ),
                                ),
                            ],
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=8, total_tokens=18),
            )

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, api_key: str):
            assert api_key == "sk-test"
            self.chat = FakeChat()

    monkeypatch.setattr("fleet_health_orchestrator.chat_orchestrator.OpenAI", FakeOpenAI)

    settings = SimpleNamespace(
        llm_chat_enabled=True,
        openai_api_key="sk-test",
        llm_chat_model="gpt-4o-mini",
        llm_chat_temperature=0.2,
        llm_chat_max_output_tokens=400,
        chat_tool_max_calls_per_turn=1,
        llm_chat_input_cost_per_1k_tokens_usd=0.0,
        llm_chat_output_cost_per_1k_tokens_usd=0.0,
    )

    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=_FakeRetrievalBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )
    orchestrator = ChatToolOrchestrator(
        logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
        settings=settings,
        mcp_adapter=adapter,
    )

    result = orchestrator.run_turn(
        user_content="What should I do?",
        session=SimpleNamespace(session_id="chat_1", incident_id=None),
        chat_history=[],
    )

    assert result is not None
    assert result.action == "tool_limit"
    assert result.action_status == "error"
    assert result.action_payload["max_tool_calls"] == 1
    assert result.action_payload["executed_tool_calls"] == 1
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["tool_name"] == "search_operational_context"


def test_chat_orchestrator_surfaces_malformed_tool_arguments(monkeypatch) -> None:
    responses = iter(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="tool_bad_json",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="search_operational_context",
                                        arguments='{"query":',
                                    ),
                                )
                            ],
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=8, total_tokens=18),
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="I could not run that tool call because the arguments were malformed.",
                            tool_calls=[],
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=8, total_tokens=18),
            ),
        ]
    )

    class FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            return next(responses)

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, api_key: str):
            assert api_key == "sk-test"
            self.chat = FakeChat()

    monkeypatch.setattr("fleet_health_orchestrator.chat_orchestrator.OpenAI", FakeOpenAI)

    settings = SimpleNamespace(
        llm_chat_enabled=True,
        openai_api_key="sk-test",
        llm_chat_model="gpt-4o-mini",
        llm_chat_temperature=0.2,
        llm_chat_max_output_tokens=400,
        chat_tool_max_calls_per_turn=4,
        llm_chat_input_cost_per_1k_tokens_usd=0.0,
        llm_chat_output_cost_per_1k_tokens_usd=0.0,
    )

    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=_FakeRetrievalBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )
    orchestrator = ChatToolOrchestrator(
        logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
        settings=settings,
        mcp_adapter=adapter,
    )

    result = orchestrator.run_turn(
        user_content="What should I do?",
        session=SimpleNamespace(session_id="chat_1", incident_id=None),
        chat_history=[],
    )

    assert result is not None
    assert result.content == "I could not run that tool call because the arguments were malformed."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["error"] == "Tool arguments are not valid JSON: Expecting value."
    assert result.trace_spans[1]["status"] == "error"


def test_mcp_adapter_enforces_tool_timeout() -> None:
    class SlowBackend:
        def search(self, query: str, documents: list[dict[str, object]], limit: int = 5):
            _ = (query, documents, limit)
            time.sleep(0.05)
            return []

    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=SlowBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        tool_timeout_seconds=0.01,
    )

    result = adapter.call_tool("search_operational_context", {"query": "battery"})

    assert result.error is not None
    assert "timed out" in result.error.lower()


def test_mcp_adapter_http_json_transport_for_incident_read(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload: dict[str, object], status_code: int = 200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, timeout=None, params=None):
        _ = (timeout, params)
        assert url.endswith("/v1/incidents/inc_123")
        return FakeResponse({"incident_id": "inc_123", "status": "open"})

    monkeypatch.setattr("fleet_health_orchestrator.mcp_client_adapter.httpx.get", fake_get)

    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=_FakeRetrievalBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        transport="http_json",
    )

    result = adapter.call_tool("read_incident", {"incident_id": "inc_123"})

    assert result.error is None
    assert result.output["incident"]["incident_id"] == "inc_123"


def test_mcp_adapter_http_json_lookup_device_health_reads_events_directly(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: list[dict[str, object]], status_code: int = 200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, timeout=None, params=None):
        calls.append({"url": url, "timeout": timeout, "params": params})
        assert url.endswith("/v1/events")
        return FakeResponse(
            [
                {"device_id": "robot-03", "value": 80.0, "threshold": 65.0},
                {"device_id": "robot-07", "value": 10.0, "threshold": 65.0},
            ]
        )

    monkeypatch.setattr("fleet_health_orchestrator.mcp_client_adapter.httpx.get", fake_get)

    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=_FakeRetrievalBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        transport="http_json",
    )

    result = adapter.call_tool("lookup_device_health", {"device_id": "robot-03"})

    assert result.error is None
    assert len(calls) == 1
    assert result.output["status"] == "anomalous"
    assert result.output["latest_event"]["device_id"] == "robot-03"


def test_mcp_adapter_http_json_includes_upstream_error_detail(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, status_code: int = 503):
            self.status_code = status_code

        def json(self):
            return {
                "detail": "Repository check failed.",
                "error": {"code": "service_not_ready", "message": "Repository check failed."},
            }

        def raise_for_status(self) -> None:
            request = httpx.Request("GET", "http://127.0.0.1:8000/v1/incidents")
            raise httpx.HTTPStatusError("service unavailable", request=request, response=self)

    def fake_get(url: str, timeout=None, params=None):
        _ = (timeout, params)
        assert url.endswith("/v1/incidents")
        return FakeResponse()

    monkeypatch.setattr("fleet_health_orchestrator.mcp_client_adapter.httpx.get", fake_get)

    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=_FakeRetrievalBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        transport="http_json",
    )

    result = adapter.call_tool("list_incidents", {})

    assert result.error is not None
    assert "HTTP 503" in result.error
    assert "Repository check failed." in result.error


def test_mcp_adapter_http_json_surfaces_timeout_with_context(monkeypatch) -> None:
    def fake_get(url: str, timeout=None, params=None):
        _ = (timeout, params)
        request = httpx.Request("GET", url)
        raise httpx.TimeoutException("timed out", request=request)

    monkeypatch.setattr("fleet_health_orchestrator.mcp_client_adapter.httpx.get", fake_get)

    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=_FakeRetrievalBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        transport="http_json",
    )

    result = adapter.call_tool("list_incidents", {})

    assert result.error is not None
    assert "timed out" in result.error
    assert "list_incidents request" in result.error


def test_mcp_adapter_http_json_surfaces_request_errors_with_context(monkeypatch) -> None:
    def fake_get(url: str, timeout=None, params=None):
        _ = (timeout, params)
        request = httpx.Request("GET", url)
        raise httpx.RequestError("connection refused", request=request)

    monkeypatch.setattr("fleet_health_orchestrator.mcp_client_adapter.httpx.get", fake_get)

    adapter = MCPClientAdapter(
        repository=_FakeRepo(),
        retrieval_backend=_FakeRetrievalBackend(),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        transport="http_json",
    )

    result = adapter.call_tool("query_device_events", {"device_id": "robot-03"})

    assert result.error is not None
    assert "query_device_events request" in result.error
    assert "connection refused" in result.error
