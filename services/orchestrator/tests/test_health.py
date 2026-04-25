import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient


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
