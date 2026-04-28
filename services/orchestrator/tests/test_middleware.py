import importlib

from fastapi.testclient import TestClient


def _build_client(tmp_path, monkeypatch: object, env: dict[str, str] | None = None) -> TestClient:
    monkeypatch.setenv("FLEET_DB_PATH", str(tmp_path / "test_fleet_health_middleware.db"))
    if env:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
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


def test_auth_required_rejects_missing_actor_header(tmp_path, monkeypatch) -> None:
    client = _build_client(
        tmp_path,
        monkeypatch,
        env={
            "FLEET_AUTH_REQUIRED": "true",
        },
    )

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 401
    assert payload["error"]["code"] == "authentication_required"


def test_auth_required_allows_request_with_actor_header(tmp_path, monkeypatch) -> None:
    client = _build_client(
        tmp_path,
        monkeypatch,
        env={
            "FLEET_AUTH_REQUIRED": "true",
        },
    )

    response = client.get("/health", headers={"x-actor-id": "user_123"})

    assert response.status_code == 200
    assert response.headers.get("x-actor-id") == "user_123"


def test_tenant_scope_enforced_when_enabled(tmp_path, monkeypatch) -> None:
    client = _build_client(
        tmp_path,
        monkeypatch,
        env={
            "FLEET_AUTH_REQUIRED": "true",
            "FLEET_AUTH_ENFORCE_TENANT_SCOPE": "true",
        },
    )

    response = client.get("/health", headers={"x-actor-id": "user_456"})
    payload = response.json()

    assert response.status_code == 401
    assert payload["error"]["code"] == "tenant_scope_required"
