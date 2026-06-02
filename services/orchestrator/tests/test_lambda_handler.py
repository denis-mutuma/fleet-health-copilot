import importlib

import pytest


pytest.importorskip("mangum")


def test_lambda_demo_imports_handler_and_seeds_data(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("FLEET_DATABASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FLEET_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("FLEET_LAMBDA_DEMO", "true")
    monkeypatch.setenv("FLEET_DB_PATH", str(tmp_path / "lambda-demo.db"))
    monkeypatch.setenv("FLEET_RETRIEVAL_BACKEND", "lexical")
    monkeypatch.setenv("FLEET_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("FLEET_LLM_CHAT_ENABLED", "false")
    monkeypatch.setenv("FLEET_OPENAI_REPORT_REFINE", "false")
    monkeypatch.setenv("FLEET_OPENAI_DIAGNOSIS_ENRICH", "false")
    monkeypatch.setenv("FLEET_AUDIT_RETENTION_SWEEP_INTERVAL_SECONDS", "0")

    handler_module = importlib.import_module("fleet_health_orchestrator.lambda_handler")
    handler_module = importlib.reload(handler_module)

    dependencies = handler_module.app.state.dependencies

    assert handler_module.handler.__class__.__name__ == "Mangum"
    assert dependencies.settings.lambda_demo_enabled is True
    assert dependencies.settings.effective_embedding_provider == "hash"
    assert dependencies.settings.effective_llm_chat_enabled is False
    assert len(dependencies.repository.list_incidents()) >= 1
    assert dependencies.repository.list_rag_documents()[0]["document_id"] == "rb_battery_thermal_demo"


def test_lambda_handler_is_mangum_adapter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEET_LAMBDA_DEMO", "true")
    monkeypatch.setenv("FLEET_DB_PATH", str(tmp_path / "lambda-adapter.db"))

    handler_module = importlib.import_module("fleet_health_orchestrator.lambda_handler")
    handler_module = importlib.reload(handler_module)

    assert handler_module.handler.__class__.__name__ == "Mangum"
