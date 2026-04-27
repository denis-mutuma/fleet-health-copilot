from types import SimpleNamespace

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
        llm_chat_model="gpt-5.4-mini",
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
        llm_chat_model="gpt-5.4-mini",
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

    assert result is not None
    assert result.content == "Use the battery thermal runbook."
    assert result.action == "rag_answer"
    assert result.action_status == "success"
