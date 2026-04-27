import importlib

from fastapi.testclient import TestClient


def _build_client(tmp_path, monkeypatch: object) -> TestClient:
    monkeypatch.setenv("FLEET_DB_PATH", str(tmp_path / "test_fleet_health_middleware.db"))
    main_module = importlib.import_module("fleet_health_orchestrator.main")
    main_module = importlib.reload(main_module)
    return TestClient(main_module.app)


def test_correlation_id_generated_when_missing(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    response = client.get("/health")

    assert response.status_code == 200
    correlation_id = response.headers.get("x-correlation-id")
    assert correlation_id is not None
    assert correlation_id.startswith("req_")


def test_correlation_id_propagated_when_provided(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    expected = "demo-correlation-id-123"
    response = client.get("/health", headers={"X-Correlation-ID": expected})

    assert response.status_code == 200
    assert response.headers.get("x-correlation-id") == expected


def test_openapi_and_docs_endpoints_available(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    openapi_response = client.get("/openapi.json")
    docs_response = client.get("/docs")

    assert openapi_response.status_code == 200
    assert openapi_response.json().get("openapi", "").startswith("3.")
    assert docs_response.status_code == 200
