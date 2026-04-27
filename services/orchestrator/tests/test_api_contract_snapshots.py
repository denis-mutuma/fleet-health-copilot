import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient


def _build_client(tmp_path, monkeypatch: object) -> TestClient:
    monkeypatch.setenv("FLEET_DB_PATH", str(tmp_path / "test_fleet_health_contracts.db"))
    main_module = importlib.import_module("fleet_health_orchestrator.main")
    main_module = importlib.reload(main_module)
    return TestClient(main_module.app)


def _load_snapshots() -> dict[str, object]:
    snapshot_file = Path(__file__).parent / "snapshots" / "api_error_contracts.json"
    return json.loads(snapshot_file.read_text(encoding="utf-8"))


def test_api_contract_snapshot_incident_not_found(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    snapshots = _load_snapshots()
    expected = snapshots["incident_not_found"]

    response = client.get("/v1/incidents/inc_missing")

    assert response.status_code == expected["status_code"]
    assert response.json() == expected["body"]


def test_api_contract_snapshot_non_anomalous_event(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    snapshots = _load_snapshots()
    expected = snapshots["non_anomalous_event"]

    response = client.post(
        "/v1/orchestrate/event",
        json={
            "event_id": "evt_no_anomaly_snapshot",
            "fleet_id": "fleet-alpha",
            "device_id": "robot-03",
            "timestamp": "2026-04-24T08:00:00Z",
            "metric": "battery_temp_c",
            "value": 60.0,
            "threshold": 65.0,
            "severity": "low",
            "tags": ["battery", "thermal"],
        },
    )

    assert response.status_code == expected["status_code"]
    assert response.json() == expected["body"]


def test_api_contract_snapshot_invalid_status_validation_error(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    snapshots = _load_snapshots()
    expected = snapshots["invalid_status_validation_error"]

    response = client.patch(
        "/v1/incidents/inc_missing",
        json={"status": "closed"},
    )
    payload = response.json()

    assert response.status_code == expected["status_code"]
    assert payload["error"]["code"] == expected["body"]["error"]["code"]
    assert payload["error"]["message"] == expected["body"]["error"]["message"]
    assert "details" in payload["error"]
    assert "errors" in payload["error"]["details"]
    assert isinstance(payload["detail"], list)
    assert len(payload["detail"]) > 0
    assert payload["detail"][0]["loc"] == expected["body"]["first_detail"]["loc"]
    assert payload["detail"][0]["type"] == expected["body"]["first_detail"]["type"]
