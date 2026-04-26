import importlib
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fleet_health_orchestrator.agents import PlanResult, VerifierAgent
from fleet_health_orchestrator.embeddings import create_query_embedder
from fleet_health_orchestrator.models import RetrievalHit
from fleet_health_orchestrator.rag import (
    LexicalRetrievalBackend,
    S3VectorsRetrievalBackend,
    build_retrieval_backend
)


def _build_client(tmp_path, monkeypatch: object) -> TestClient:
    monkeypatch.setenv("FLEET_DB_PATH", str(tmp_path / "test_fleet_health.db"))
    main_module = importlib.import_module("fleet_health_orchestrator.main")
    main_module = importlib.reload(main_module)
    return TestClient(main_module.app)


def _load_evaluate_pipeline():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_pipeline.py"
    spec = importlib.util.spec_from_file_location("evaluate_pipeline", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lexical_retrieval_backend_ranks_and_limits_hits() -> None:
    backend = LexicalRetrievalBackend()
    documents = [
        {
            "document_id": "rb_motor_current_v1",
            "source": "runbook",
            "title": "Motor Current Spike Triage",
            "content": "motor current current actuator",
            "tags": ["motor", "current"]
        },
        {
            "document_id": "rb_battery_thermal_v2",
            "source": "runbook",
            "title": "Battery Thermal Drift Response",
            "content": "battery thermal cooling",
            "tags": ["battery", "thermal"]
        }
    ]

    hits = backend.search(
        query="motor current spike",
        documents=documents,
        limit=1
    )

    assert len(hits) == 1
    assert hits[0].document_id == "rb_motor_current_v1"


def test_retrieval_backend_factory_defaults_to_lexical() -> None:
    backend = build_retrieval_backend()

    assert isinstance(backend, LexicalRetrievalBackend)


def test_retrieval_backend_factory_builds_s3vectors_with_bucket_and_index() -> None:
    backend = build_retrieval_backend(
        backend_name="s3vectors",
        s3_vectors_bucket="fleet-health-vectors",
        s3_vectors_index="runbooks"
    )

    assert isinstance(backend, S3VectorsRetrievalBackend)
    assert backend.bucket_name == "fleet-health-vectors"
    assert backend.index_name == "runbooks"
    assert backend.index_arn is None


def test_retrieval_backend_factory_accepts_index_arn_only() -> None:
    arn = "arn:aws:s3vectors:us-east-1:123456789012:index/runbooks"
    backend = build_retrieval_backend(
        backend_name="s3vectors",
        s3_vectors_index_arn=arn
    )

    assert isinstance(backend, S3VectorsRetrievalBackend)
    assert backend.index_arn == arn
    assert backend.bucket_name == ""
    assert backend.index_name == ""


def test_retrieval_backend_factory_rejects_fixed_vector_wrong_dim() -> None:
    with pytest.raises(ValueError, match="length"):
        build_retrieval_backend(
            backend_name="s3vectors",
            s3_vectors_bucket="b",
            s3_vectors_index="i",
            s3_vectors_embedding_dimension=2,
            s3_vectors_query_vector_json="[1.0]"
        )


def test_s3_vectors_backend_queries_and_maps_hits() -> None:
    calls: list[dict[str, object]] = []

    class FakeClient:
        def query_vectors(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            return {
                "vectors": [
                    {
                        "key": "k1",
                        "distance": 0.25,
                        "metadata": {
                            "document_id": "doc_1",
                            "title": "From Meta",
                            "source": "runbook",
                            "excerpt": "meta excerpt"
                        }
                    }
                ],
                "distanceMetric": "cosine"
            }

    backend = S3VectorsRetrievalBackend(
        "bucket",
        "index",
        embedding_dimension=8,
        client=FakeClient()
    )
    documents = [
        {
            "document_id": "doc_1",
            "title": "Corpus Title",
            "source": "incident",
            "content": "fallback body text for excerpt"
        }
    ]
    hits = backend.search("motor fault", documents=documents, limit=3)

    assert calls[0]["vectorBucketName"] == "bucket"
    assert calls[0]["indexName"] == "index"
    assert calls[0]["topK"] == 3
    assert len(calls[0]["queryVector"]["float32"]) == 8

    assert len(hits) == 1
    assert hits[0].document_id == "doc_1"
    assert hits[0].title == "From Meta"
    assert hits[0].excerpt == "meta excerpt"
    assert hits[0].score == pytest.approx(0.75)


def test_s3_vectors_backend_fills_fields_from_corpus_when_metadata_sparse() -> None:
    class FakeClient:
        def query_vectors(self, **kwargs: object) -> dict[str, object]:
            return {
                "vectors": [{"key": "doc_2", "distance": 1.0, "metadata": {}}],
                "distanceMetric": "euclidean"
            }

    backend = S3VectorsRetrievalBackend(
        "b",
        "i",
        embedding_dimension=4,
        client=FakeClient()
    )
    documents = [
        {
            "document_id": "doc_2",
            "title": "Corpus Only",
            "source": "runbook",
            "content": "alpha beta gamma delta epsilon"
        }
    ]
    hits = backend.search("q", documents=documents, limit=5)

    assert hits[0].document_id == "doc_2"
    assert hits[0].title == "Corpus Only"
    assert hits[0].source == "runbook"
    assert hits[0].excerpt == "alpha beta gamma delta epsilon"[:240]


def test_s3_vectors_backend_prefers_index_arn_in_request() -> None:
    calls: list[dict[str, object]] = []

    class FakeClient:
        def query_vectors(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            return {"vectors": [], "distanceMetric": "cosine"}

    arn = "arn:aws:s3vectors:us-east-1:123456789012:index/runbooks"
    backend = S3VectorsRetrievalBackend(
        "",
        "",
        index_arn=arn,
        embedding_dimension=4,
        client=FakeClient()
    )
    backend.search("x", documents=[], limit=2)

    assert calls[0]["indexArn"] == arn
    assert "vectorBucketName" not in calls[0]


def test_retrieval_backend_factory_requires_s3vectors_config() -> None:
    with pytest.raises(ValueError, match="FLEET_S3_VECTORS"):
        build_retrieval_backend(backend_name="s3vectors")


def test_health_endpoint(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_event_ingestion_and_listing(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    payload = {
        "event_id": "evt_test_1",
        "fleet_id": "fleet-alpha",
        "device_id": "robot-03",
        "timestamp": "2026-04-24T08:00:00Z",
        "metric": "battery_temp_c",
        "value": 74.2,
        "threshold": 65.0,
        "severity": "high",
        "tags": ["battery", "thermal"]
    }

    ingest_response = client.post("/v1/events", json=payload)
    list_response = client.get("/v1/events")

    assert ingest_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()[0]["event_id"] == "evt_test_1"


def test_rag_index_and_search(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    document_payload = {
        "document_id": "rb_battery_thermal_v2",
        "source": "runbook",
        "title": "Battery Thermal Drift Response",
        "content": "Reduce duty cycle and inspect cooling system when battery thermal drift repeats.",
        "tags": ["battery", "thermal"]
    }

    upsert_response = client.post("/v1/rag/documents", json=document_payload)
    search_response = client.get("/v1/rag/search", params={"query": "battery thermal drift"})

    assert upsert_response.status_code == 200
    assert search_response.status_code == 200
    assert search_response.json()[0]["document_id"] == "rb_battery_thermal_v2"


def test_orchestration_endpoint(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    client.post(
        "/v1/rag/documents",
        json={
            "document_id": "rb_battery_thermal_v2",
            "source": "runbook",
            "title": "Battery Thermal Drift Response",
            "content": "Reduce duty cycle by twenty percent for thermal drift.",
            "tags": ["battery", "thermal"]
        }
    )

    response = client.post(
        "/v1/orchestrate/event",
        json={
            "event_id": "evt_orch_1",
            "fleet_id": "fleet-alpha",
            "device_id": "robot-03",
            "timestamp": "2026-04-24T08:00:00Z",
            "metric": "battery_temp_c",
            "value": 80.0,
            "threshold": 65.0,
            "severity": "high",
            "tags": ["battery", "thermal"]
        }
    )

    assert response.status_code == 200
    assert response.json()["device_id"] == "robot-03"
    assert response.json()["evidence"]["runbooks"] == ["rb_battery_thermal_v2"]
    assert response.json()["recommended_actions"][0].startswith(
        "Follow rb_battery_thermal_v2:"
    )


def test_get_incident_by_id(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    create_response = client.post(
        "/v1/orchestrate/event",
        json={
            "event_id": "evt_lookup_1",
            "fleet_id": "fleet-alpha",
            "device_id": "robot-03",
            "timestamp": "2026-04-24T08:00:00Z",
            "metric": "battery_temp_c",
            "value": 80.0,
            "threshold": 65.0,
            "severity": "high",
            "tags": ["battery", "thermal"]
        }
    )
    incident_id = create_response.json()["incident_id"]

    response = client.get(f"/v1/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["incident_id"] == incident_id


def test_get_incident_by_id_returns_404_for_unknown_id(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.get("/v1/incidents/inc_missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found."


def test_update_incident_status(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    create_response = client.post(
        "/v1/orchestrate/event",
        json={
            "event_id": "evt_status_1",
            "fleet_id": "fleet-alpha",
            "device_id": "robot-03",
            "timestamp": "2026-04-24T08:00:00Z",
            "metric": "battery_temp_c",
            "value": 80.0,
            "threshold": 65.0,
            "severity": "high",
            "tags": ["battery", "thermal"]
        }
    )
    incident_id = create_response.json()["incident_id"]

    response = client.patch(
        f"/v1/incidents/{incident_id}",
        json={"status": "acknowledged"}
    )
    lookup_response = client.get(f"/v1/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"
    assert lookup_response.json()["status"] == "acknowledged"


def test_update_incident_status_returns_404_for_unknown_id(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.patch(
        "/v1/incidents/inc_missing",
        json={"status": "resolved"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found."


def test_update_incident_status_rejects_unknown_status(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.patch(
        "/v1/incidents/inc_missing",
        json={"status": "closed"}
    )

    assert response.status_code == 422


def test_orchestration_rejects_non_anomalous_event(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.post(
        "/v1/orchestrate/event",
        json={
            "event_id": "evt_no_anomaly_1",
            "fleet_id": "fleet-alpha",
            "device_id": "robot-03",
            "timestamp": "2026-04-24T08:00:00Z",
            "metric": "battery_temp_c",
            "value": 60.0,
            "threshold": 65.0,
            "severity": "low",
            "tags": ["battery", "thermal"]
        }
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Event does not exceed threshold."


def test_orchestration_reports_empty_evidence_without_rag(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.post(
        "/v1/orchestrate/event",
        json={
            "event_id": "evt_no_rag_1",
            "fleet_id": "fleet-alpha",
            "device_id": "robot-03",
            "timestamp": "2026-04-24T08:00:00Z",
            "metric": "battery_temp_c",
            "value": 80.0,
            "threshold": 65.0,
            "severity": "high",
            "tags": ["battery", "thermal"]
        }
    )

    assert response.status_code == 200
    assert response.json()["evidence"]["runbooks"] == []
    assert response.json()["evidence"]["matched_incidents"] == []
    assert response.json()["recommended_actions"] == [
        "Review recent telemetry for repeated threshold crossings",
        "Have an operator inspect the device before returning to normal duty cycle"
    ]


def test_invalid_event_payload_returns_422(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.post(
        "/v1/events",
        json={
            "event_id": "evt_invalid_1",
            "fleet_id": "fleet-alpha",
            "device_id": "robot-03",
            "timestamp": "2026-04-24T08:00:00Z",
            "metric": "battery_temp_c",
            "value": 70.0,
            "threshold": 65.0,
            "severity": "urgent",
            "tags": ["battery", "thermal"]
        }
    )

    assert response.status_code == 422


def test_metrics_endpoint(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.get("/v1/metrics")

    assert response.status_code == 200
    assert "events_ingested_total" in response.json()


def test_evaluate_pipeline_reports_confusion_metrics(tmp_path, monkeypatch) -> None:
    evaluate_pipeline = _load_evaluate_pipeline()
    events_file = tmp_path / "events.jsonl"
    events = [
        {"event_id": "evt_tp", "value": 80.0, "threshold": 65.0},
        {"event_id": "evt_fp", "value": 20.0, "threshold": 65.0},
        {"event_id": "evt_fn", "value": 90.0, "threshold": 65.0},
        {"event_id": "evt_tn", "value": 30.0, "threshold": 65.0}
    ]
    events_file.write_text(
        "\n".join(json.dumps(event) for event in events),
        encoding="utf-8"
    )
    statuses = iter([200, 200, 400, 400])

    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            raise AssertionError("unexpected non-evaluation status")

    def fake_post(*args, **kwargs) -> FakeResponse:
        return FakeResponse(next(statuses))

    monkeypatch.setattr(evaluate_pipeline.httpx, "post", fake_post)

    metrics = evaluate_pipeline.evaluate(
        events_file=events_file,
        base_url="http://127.0.0.1:8000"
    )

    assert metrics["true_positives"] == 1.0
    assert metrics["false_positives"] == 1.0
    assert metrics["false_negatives"] == 1.0
    assert metrics["true_negatives"] == 1.0
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["accuracy"] == 0.5
    assert "retrieval_mean_reciprocal_rank" in metrics
    assert "verifier_pass_rate" in metrics


def test_retrieval_reciprocal_rank_helper() -> None:
    evaluate_pipeline = _load_evaluate_pipeline()
    assert evaluate_pipeline._retrieval_reciprocal_rank(
        {"runbooks": ["noise", "rb_x"]}, "rb_x"
    ) == pytest.approx(0.5)
    assert evaluate_pipeline._retrieval_reciprocal_rank({"runbooks": ["rb_x"]}, "rb_x") == 1.0
    assert evaluate_pipeline._retrieval_reciprocal_rank({}, "rb_x") == 0.0


def test_verifier_rejects_citations_outside_retrieval() -> None:
    verifier = VerifierAgent()
    hits = [
        RetrievalHit(
            document_id="rb_good",
            source="runbook",
            title="Good",
            score=1.0,
            excerpt="text"
        )
    ]
    plan = PlanResult(actions=["Follow rb_wrong: inspect everything."])
    result = verifier.verify(plan=plan, hits=hits)
    assert result.passed is False
    assert any("rb_wrong" in warning for warning in result.warnings)


def test_hash_embedding_produces_expected_dimension() -> None:
    embed = create_query_embedder(24, provider="hash")
    assert len(embed("battery thermal drift")) == 24


def test_openai_embedding_provider_calls_api(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleet_health_orchestrator import embeddings as embeddings_mod

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": [{"embedding": [0.25, 0.75]}]}

    monkeypatch.setattr(embeddings_mod.httpx, "post", lambda *a, **k: FakeResponse())
    embed = embeddings_mod.create_query_embedder(
        2,
        provider="openai",
        openai_api_key="sk-test",
        openai_model="text-embedding-3-small"
    )
    assert embed("hello") == [0.25, 0.75]
