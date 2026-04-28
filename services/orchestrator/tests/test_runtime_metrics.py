from fleet_health_orchestrator.metrics import RuntimeMetrics


def test_runtime_metrics_preserves_flat_dict_access() -> None:
    metrics = RuntimeMetrics()

    metrics["events_ingested_total"] += 1
    metrics["orchestration_latency_ms_last"] = 42.5

    snapshot = metrics.copy()
    assert snapshot["events_ingested_total"] == 1.0
    assert snapshot["orchestration_latency_ms_last"] == 42.5


def test_runtime_metrics_observes_request_latency() -> None:
    metrics = RuntimeMetrics()

    metrics.observe_request(18.5)

    snapshot = metrics.copy()
    assert snapshot["requests_total"] == 1.0
    assert snapshot["request_latency_ms_last"] == 18.5


def test_runtime_metrics_observes_rag_query_latency_and_count() -> None:
    metrics = RuntimeMetrics()

    metrics.observe_rag_query(87.2)

    snapshot = metrics.copy()
    assert snapshot["rag_queries_total"] == 1.0
    assert snapshot["rag_query_latency_ms_last"] == 87.2


def test_runtime_metrics_observes_llm_chat_turn_cost_and_latency() -> None:
    metrics = RuntimeMetrics()

    metrics.observe_llm_chat_turn(latency_ms=155.0, cost_usd=0.0125)

    snapshot = metrics.copy()
    assert snapshot["llm_chat_turns_total"] == 1.0
    assert snapshot["llm_chat_turn_latency_ms_last"] == 155.0
    assert snapshot["llm_chat_turn_cost_usd_last"] == 0.0125


def test_runtime_metrics_renders_prometheus_text() -> None:
    metrics = RuntimeMetrics()
    metrics.observe_request(18.5)
    metrics.observe_orchestration(120.0)
    metrics.observe_llm_chat_turn(latency_ms=155.0, cost_usd=0.0125)

    rendered = metrics.render_prometheus()

    assert "requests_total 1" in rendered
    assert "request_latency_ms_bucket" in rendered
    assert "orchestration_latency_ms_bucket" in rendered
    assert "llm_chat_turn_cost_usd_bucket" in rendered