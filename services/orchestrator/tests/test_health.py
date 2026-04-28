import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from fleet_health_orchestrator.agents import PlanResult, VerifierAgent
from fleet_health_orchestrator.embeddings import create_query_embedder
from fleet_health_orchestrator.ingestion import delete_documents_from_s3_vectors, extract_text_from_bytes
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


def _load_script_module(module_name: str, file_name: str):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / file_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
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


def test_create_query_embedder_uses_openai_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key
            self.embeddings = SimpleNamespace(create=self._create)

        def _create(self, *, model: str, input: str) -> object:
            assert model == "text-embedding-3-large"
            assert input == "battery thermal drift"
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3, 0.4])])

    monkeypatch.setattr("fleet_health_orchestrator.embeddings.OpenAI", FakeClient)

    embed = create_query_embedder(
        4,
        provider="openai",
        openai_api_key="sk-test",
        openai_model="text-embedding-3-large",
    )

    assert embed("battery thermal drift") == [0.1, 0.2, 0.3, 0.4]


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


def test_ready_endpoint(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_cors_reflects_configured_origin(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEET_CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("FLEET_DB_PATH", str(tmp_path / "cors.db"))
    main_module = importlib.import_module("fleet_health_orchestrator.main")
    main_module = importlib.reload(main_module)
    client = TestClient(main_module.app)
    response = client.get(
        "/health",
        headers={"Origin": "https://app.example.com"}
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_cors_not_enabled_without_env(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FLEET_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("FLEET_DB_PATH", str(tmp_path / "no_cors.db"))
    main_module = importlib.import_module("fleet_health_orchestrator.main")
    main_module = importlib.reload(main_module)
    client = TestClient(main_module.app)
    response = client.get(
        "/health",
        headers={"Origin": "https://app.example.com"}
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


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
    assert upsert_response.json()["chunk_count"] >= 1
    assert search_response.status_code == 200
    assert search_response.json()[0]["document_id"].startswith("rb_battery_thermal_v2")


def test_rag_upload_document_endpoint(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    content = "Battery thermal drift requires reduced duty cycle and cooling inspection. " * 60

    response = client.post(
        "/v1/rag/documents/upload",
        data={
            "source": "runbook",
            "tags": "battery,thermal,operations",
            "chunk_size_chars": "400",
            "chunk_overlap_chars": "80",
        },
        files={"file": ("runbook.md", content, "text/markdown")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chunk_count"] > 1
    assert payload["indexed_chunks"] == 0
    assert payload["embedding_model"] == "text-embedding-3-large"


def test_rag_upload_document_async_and_status(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    content = "Battery thermal drift playbook section. " * 80

    create = client.post(
        "/v1/rag/documents/upload/async",
        data={
            "source": "runbook",
            "tags": "battery,thermal",
            "chunk_size_chars": "500",
            "chunk_overlap_chars": "100",
        },
        files={"file": ("async-runbook.md", content, "text/markdown")},
        headers={"Idempotency-Key": "idem-rag-1"},
    )
    assert create.status_code == 200
    job = create.json()
    assert job["job_id"].startswith("job_")

    fetched = client.get(f"/v1/rag/ingestion-jobs/{job['job_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] in ("pending", "running", "succeeded")

    again = client.post(
        "/v1/rag/documents/upload/async",
        data={"source": "runbook"},
        files={"file": ("async-runbook.md", content, "text/markdown")},
        headers={"Idempotency-Key": "idem-rag-1"},
    )
    assert again.status_code == 200
    assert again.json()["job_id"] == job["job_id"]


def test_extract_text_from_html_bytes() -> None:
    html = b"<html><body><h1>Thermal</h1><p>Battery drift mitigation steps.</p></body></html>"
    extracted = extract_text_from_bytes("runbook.html", html)
    assert "Thermal" in extracted
    assert "Battery drift mitigation steps." in extracted


def test_rag_document_families_listing(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    first = client.post(
        "/v1/rag/documents",
        json={
            "document_id": "rb_battery_thermal_v2",
            "source": "runbook",
            "title": "Battery Thermal Drift Response",
            "content": "thermal " * 900,
            "tags": ["battery", "thermal"],
        },
    )
    second = client.post(
        "/v1/rag/documents",
        json={
            "document_id": "rb_motor_current_v1",
            "source": "runbook",
            "title": "Motor Current Spike Triage",
            "content": "motor current " * 300,
            "tags": ["motor", "current"],
        },
    )
    listing = client.get("/v1/rag/documents")

    assert first.status_code == 200
    assert second.status_code == 200
    assert listing.status_code == 200
    payload = listing.json()
    assert any(item["document_id"] == "rb_battery_thermal_v2" and item["chunk_count"] >= 2 for item in payload)
    assert any(item["document_id"] == "rb_motor_current_v1" and item["chunk_count"] >= 1 for item in payload)


def test_rag_document_family_delete(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    created = client.post(
        "/v1/rag/documents",
        json={
            "document_id": "rb_delete_me",
            "source": "runbook",
            "title": "Delete me",
            "content": "delete " * 900,
            "tags": ["cleanup"],
        },
    )
    deleted = client.delete("/v1/rag/documents/rb_delete_me")
    listing = client.get("/v1/rag/documents")

    assert created.status_code == 200
    assert deleted.status_code == 200
    assert deleted.json()["deleted_chunks"] >= 1
    assert all(item["document_id"] != "rb_delete_me" for item in listing.json())


def test_rag_document_family_delete_404(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.delete("/v1/rag/documents/doc_missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "RAG document not found."


def test_delete_documents_from_s3_vectors_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeClient:
        def delete_vectors(self, **kwargs: object) -> None:
            calls.append(kwargs)

    monkeypatch.setattr("fleet_health_orchestrator.ingestion.boto3.client", lambda _: FakeClient())

    deleted = delete_documents_from_s3_vectors(
        document_keys=["doc-1", "doc-2", "doc-3"],
        bucket="bucket-a",
        index="index-a",
        index_arn="",
        batch_size=2,
    )

    assert deleted == 3
    assert len(calls) == 2
    assert calls[0]["vectorBucketName"] == "bucket-a"
    assert calls[0]["indexName"] == "index-a"
    assert calls[0]["keys"] == ["doc-1", "doc-2"]
    assert calls[1]["keys"] == ["doc-3"]


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
    assert response.json()["error"]["code"] == "resource_not_found"
    assert response.json()["error"]["message"] == "Incident not found."


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
    assert response.json()["status_history"][0]["status"] == "acknowledged"
    assert response.json()["status_history"][0]["previous_status"] == "open"
    assert response.json()["audit_events"][0]["action"] == "incident.status_updated"
    assert lookup_response.json()["status"] == "acknowledged"
    assert lookup_response.json()["status_history"][0]["status"] == "acknowledged"
    assert lookup_response.json()["audit_events"][0]["details"]["to_status"] == "acknowledged"


def test_incident_creation_records_initial_history_and_audit_event(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    create_response = client.post(
        "/v1/orchestrate/event",
        json={
            "event_id": "evt_status_history_1",
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

    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["status_history"][0]["status"] == "open"
    assert payload["status_history"][0]["previous_status"] is None
    assert payload["audit_events"][0]["action"] == "incident.created"
    assert payload["audit_events"][0]["details"]["device_id"] == "robot-03"


def test_audit_endpoints_return_incident_audit_history(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    create_response = client.post(
        "/v1/orchestrate/event",
        json={
            "event_id": "evt_audit_1",
            "fleet_id": "fleet-alpha",
            "device_id": "robot-03",
            "timestamp": "2026-04-24T08:00:00Z",
            "metric": "battery_temp_c",
            "value": 80.0,
            "threshold": 65.0,
            "severity": "high",
            "tags": ["battery", "thermal"],
        },
    )
    incident_id = create_response.json()["incident_id"]

    patch_response = client.patch(
        f"/v1/incidents/{incident_id}",
        json={"status": "acknowledged", "reason": "Operator triage complete."},
    )
    assert patch_response.status_code == 200

    incident_audit = client.get(f"/v1/incidents/{incident_id}/audit-events")
    global_audit = client.get("/v1/audit/events", params={"entity_type": "incident", "entity_id": incident_id})

    assert incident_audit.status_code == 200
    assert global_audit.status_code == 200
    assert len(incident_audit.json()) >= 2
    assert incident_audit.json()[0]["entity_id"] == incident_id
    assert incident_audit.json()[0]["tenant_id"] is None
    assert global_audit.json()[0]["entity_id"] == incident_id


def test_update_incident_status_returns_404_for_unknown_id(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.patch(
        "/v1/incidents/inc_missing",
        json={"status": "resolved"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found."
    assert response.json()["error"]["code"] == "resource_not_found"
    assert response.json()["error"]["message"] == "Incident not found."


def test_update_incident_status_rejects_unknown_status(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.patch(
        "/v1/incidents/inc_missing",
        json={"status": "closed"}
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Request payload validation failed."
    assert isinstance(payload["detail"], list)


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
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["message"] == "Event does not exceed threshold."


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
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Request payload validation failed."
    assert isinstance(payload["detail"], list)


def test_metrics_endpoint(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.get("/v1/metrics")

    assert response.status_code == 200
    assert "events_ingested_total" in response.json()


def test_metrics_endpoint_includes_request_counter_after_request(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    health = client.get("/health")
    assert health.status_code == 200

    response = client.get("/v1/metrics")

    assert response.status_code == 200
    assert response.json()["requests_total"] >= 1.0


def test_prometheus_metrics_endpoint_renders_histograms(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    warmup = client.get("/health")
    assert warmup.status_code == 200

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "requests_total" in body
    assert "request_latency_ms_bucket" in body
    assert "orchestration_latency_ms_bucket" in body


def test_chat_session_lifecycle_and_rag_citations(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    client.post(
        "/v1/rag/documents",
        json={
            "document_id": "rb_battery_thermal_v2",
            "source": "runbook",
            "title": "Battery Thermal Drift Response",
            "content": "Reduce duty cycle and inspect cooling lines for thermal drift incidents.",
            "tags": ["battery", "thermal"],
        },
    )

    created = client.post("/v1/chat/sessions", json={"incident_id": None})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    posted = client.post(
        f"/v1/chat/sessions/{session_id}/messages",
        json={"content": "What should I do for battery thermal drift?"},
    )
    assert posted.status_code == 200
    conversation = posted.json()
    assert conversation["session"]["session_id"] == session_id
    assert len(conversation["messages"]) >= 2
    assert conversation["messages"][-1]["role"] == "assistant"
    assert len(conversation["messages"][-1]["citations"]) >= 1


def test_chat_session_rejects_missing_incident_reference(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    response = client.post("/v1/chat/sessions", json={"incident_id": "inc_missing"})

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "resource_not_found"
    assert payload["error"]["message"] == "Incident not found."
    assert payload["error"]["details"] == {"incident_id": "inc_missing"}


def test_chat_actions_update_status_and_simulate(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    created = client.post("/v1/chat/sessions", json={"incident_id": None})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    created_incident = client.post(
        "/v1/orchestrate/event",
        json={
            "event_id": "evt_chat_action_1",
            "fleet_id": "fleet-alpha",
            "device_id": "robot-03",
            "timestamp": "2026-04-24T08:00:00Z",
            "metric": "battery_temp_c",
            "value": 80.0,
            "threshold": 65.0,
            "severity": "high",
            "tags": ["battery", "thermal"],
        },
    )
    incident_id = created_incident.json()["incident_id"]

    status_update = client.post(
        f"/v1/chat/sessions/{session_id}/messages",
        json={"content": f"/status {incident_id} acknowledged"},
    )
    assert status_update.status_code == 200
    status_message = status_update.json()["messages"][-1]
    assert status_message["action"] == "update_status"
    assert status_message["action_status"] == "success"

    simulate = client.post(
        f"/v1/chat/sessions/{session_id}/messages",
        json={"content": "/simulate"},
    )
    assert simulate.status_code == 200
    simulate_message = simulate.json()["messages"][-1]
    assert simulate_message["action"] == "simulate"
    assert simulate_message["action_status"] == "success"


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
    assert "runbook_action_grounding_rate" in metrics


def test_evaluate_pipeline_reports_latency_metrics(tmp_path, monkeypatch) -> None:
    evaluate_pipeline = _load_evaluate_pipeline()
    events_file = tmp_path / "events.jsonl"
    events = [
        {"event_id": "evt_a", "value": 80.0, "threshold": 65.0},
        {"event_id": "evt_b", "value": 20.0, "threshold": 65.0}
    ]
    events_file.write_text(
        "\n".join(json.dumps(event) for event in events),
        encoding="utf-8"
    )
    responses = iter(
        [
            (200, {"latency_ms": 12.5, "verification": {"passed": True}}),
            (400, {})
        ]
    )

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self) -> None:
            raise AssertionError("unexpected non-evaluation status")

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_post(*args, **kwargs) -> FakeResponse:
        status_code, payload = next(responses)
        return FakeResponse(status_code, payload)

    # Use fixed perf_counter values to keep this regression check deterministic.
    perf_ticks = iter([0.0, 0.010, 1.0, 1.030])

    monkeypatch.setattr(evaluate_pipeline.httpx, "post", fake_post)
    monkeypatch.setattr(evaluate_pipeline, "perf_counter", lambda: next(perf_ticks))

    metrics = evaluate_pipeline.evaluate(
        events_file=events_file,
        base_url="http://127.0.0.1:8000"
    )

    assert metrics["average_response_latency_ms"] == pytest.approx(20.0)
    assert metrics["average_time_to_diagnosis_ms"] == pytest.approx(12.5)


def test_runbook_action_grounding_helper() -> None:
    evaluate_pipeline = _load_evaluate_pipeline()
    assert evaluate_pipeline._runbook_action_grounding({}) is None
    assert evaluate_pipeline._runbook_action_grounding(
        {"evidence": {"runbooks": []}, "recommended_actions": ["x"]}
    ) is None
    assert evaluate_pipeline._runbook_action_grounding(
        {
            "evidence": {"runbooks": ["rb_a"]},
            "recommended_actions": ["Follow rb_b: do thing"]
        }
    ) is False
    assert evaluate_pipeline._runbook_action_grounding(
        {
            "evidence": {"runbooks": ["rb_a"]},
            "recommended_actions": ["Follow rb_a: do thing"]
        }
    ) is True


def test_retrieval_reciprocal_rank_helper() -> None:
    evaluate_pipeline = _load_evaluate_pipeline()
    assert evaluate_pipeline._retrieval_reciprocal_rank(
        {"runbooks": ["noise", "rb_x"]}, "rb_x"
    ) == pytest.approx(0.5)
    assert evaluate_pipeline._retrieval_reciprocal_rank({"runbooks": ["rb_x"]}, "rb_x") == 1.0
    assert evaluate_pipeline._retrieval_reciprocal_rank({}, "rb_x") == 0.0


def test_expected_runbook_vibration() -> None:
    evaluate_pipeline = _load_evaluate_pipeline()
    event = {"tags": ["vibration", "mechanical"], "metric": "vibration_rms"}
    assert evaluate_pipeline._expected_runbook(event) == "rb_wheel_slip_traction_playbook_v2"


def test_expected_runbook_cpu() -> None:
    evaluate_pipeline = _load_evaluate_pipeline()
    event = {"tags": ["cpu", "thermal"], "metric": "cpu_temp_c"}
    assert evaluate_pipeline._expected_runbook(event) == "rb_cpu_thermal_throttle_procedure_v2"


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
    from types import SimpleNamespace

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            assert api_key == "sk-test"
            self.embeddings = SimpleNamespace(create=self._create)

        def _create(self, *, model: str, input: str) -> object:
            assert model == "text-embedding-3-large"
            assert input == "hello"
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.25, 0.75])])

    monkeypatch.setattr(embeddings_mod, "OpenAI", FakeClient)
    embed = embeddings_mod.create_query_embedder(
        2,
        provider="openai",
        openai_api_key="sk-test",
        openai_model="text-embedding-3-large"
    )
    assert embed("hello") == [0.25, 0.75]


def test_http_embedding_provider_surfaces_http_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleet_health_orchestrator import embeddings as embeddings_mod

    class ErrorResponse:
        status_code = 502

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "detail": "Embedding upstream unavailable.",
                "error": {"message": "Embedding upstream unavailable."},
            }

        def raise_for_status(self) -> None:
            request = embeddings_mod.httpx.Request("POST", "http://embeddings.local/v1/embed")
            raise embeddings_mod.httpx.HTTPStatusError(
                "bad gateway",
                request=request,
                response=self,
            )

    def fake_post(url: str, **kwargs) -> ErrorResponse:
        assert url == "http://embeddings.local/v1/embed"
        assert kwargs["json"] == {"input": "hello"}
        return ErrorResponse()

    monkeypatch.setattr(embeddings_mod.httpx, "post", fake_post)

    embed = embeddings_mod.create_query_embedder(
        2,
        provider="http",
        http_url="http://embeddings.local/v1/embed",
    )

    with pytest.raises(
        RuntimeError,
        match=r"HTTP embedding request to http://embeddings\.local/v1/embed failed with HTTP 502: Embedding upstream unavailable",
    ):
        embed("hello")


def test_evaluate_pipeline_surfaces_request_error_with_context(tmp_path, monkeypatch) -> None:
    evaluate_pipeline = _load_evaluate_pipeline()
    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        json.dumps({"event_id": "evt_1", "value": 80.0, "threshold": 65.0}),
        encoding="utf-8",
    )

    def fake_post(url: str, **kwargs):
        raise evaluate_pipeline.httpx.RequestError(
            "connection reset",
            request=evaluate_pipeline.httpx.Request("POST", url),
        )

    monkeypatch.setattr(evaluate_pipeline.httpx, "post", fake_post)

    with pytest.raises(
        RuntimeError,
        match=r"evaluate request to http://127\.0\.0\.1:8000/v1/orchestrate/event failed: connection reset",
    ):
        evaluate_pipeline.evaluate(events_file=events_file, base_url="http://127.0.0.1:8000")


def test_replay_script_surfaces_timeout_with_context(tmp_path, monkeypatch) -> None:
    replay_events = _load_script_module("replay_events", "replay_events.py")
    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        json.dumps({"event_id": "evt_1", "value": 80.0, "threshold": 65.0}),
        encoding="utf-8",
    )

    def fake_post(url: str, **kwargs):
        raise replay_events.httpx.TimeoutException(
            "timed out",
            request=replay_events.httpx.Request("POST", url),
        )

    monkeypatch.setattr(replay_events.httpx, "post", fake_post)

    with pytest.raises(
        RuntimeError,
        match=r"replay request to http://127\.0\.0\.1:8000/v1/events timed out",
    ):
        replay_events.replay(events_file, "http://127.0.0.1:8000")


def test_index_documents_script_surfaces_request_error_with_context(tmp_path, monkeypatch) -> None:
    index_documents = _load_script_module("index_documents", "index_documents.py")
    documents_file = tmp_path / "documents.jsonl"
    documents_file.write_text(
        json.dumps({"document_id": "rb_1", "title": "Runbook", "content": "content"}),
        encoding="utf-8",
    )

    def fake_post(url: str, **kwargs):
        raise index_documents.httpx.RequestError(
            "connection refused",
            request=index_documents.httpx.Request("POST", url),
        )

    monkeypatch.setattr(index_documents.httpx, "post", fake_post)

    with pytest.raises(
        RuntimeError,
        match=r"index_documents request to http://127\.0\.0\.1:8000/v1/rag/documents failed: connection refused",
    ):
        index_documents.index_documents(documents_file, "http://127.0.0.1:8000")
