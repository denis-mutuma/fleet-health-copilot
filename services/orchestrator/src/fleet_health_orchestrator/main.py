from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

from fleet_health_orchestrator.dependencies import initialize_dependencies
from fleet_health_orchestrator.endpoints import router
from fleet_health_orchestrator.exceptions import OrchestratorError
from fleet_health_orchestrator.middleware import (
    AuthContextMiddleware,
    CorrelationIDMiddleware,
    DebugLoggingMiddleware,
    RequestLoggingMiddleware,
)

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator


DEMO_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Fleet Health Lambda Demo</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f7f8fa; color: #17202a; }
    main { max-width: 980px; margin: 0 auto; padding: 32px 18px 48px; }
    header { display: flex; justify-content: space-between; gap: 16px; align-items: center; margin-bottom: 24px; }
    h1 { font-size: clamp(1.75rem, 3vw, 2.6rem); margin: 0; letter-spacing: 0; }
    button { border: 1px solid #1f6feb; background: #1f6feb; color: white; border-radius: 6px; padding: 10px 14px; font-weight: 700; cursor: pointer; }
    button.secondary { background: white; color: #1f6feb; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
    .panel { background: white; border: 1px solid #d7dde5; border-radius: 8px; padding: 16px; }
    .muted { color: #5d6b7a; }
    .status { display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 10px; background: #e8f4ed; color: #176b3a; font-weight: 700; }
    pre { white-space: pre-wrap; word-break: break-word; background: #101820; color: #eaf0f6; border-radius: 6px; padding: 12px; min-height: 96px; }
    ul { padding-left: 20px; }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Fleet Health Lambda Demo</h1>
        <p class="muted">Ephemeral AWS-only demo served by one Lambda Function URL.</p>
      </div>
      <span id="status" class="status">Checking</span>
    </header>
    <section class="grid">
      <article class="panel">
        <h2>Incidents</h2>
        <p class="muted">Seeded sample data resets with Lambda storage.</p>
        <button onclick="loadIncidents()">Refresh</button>
        <button class="secondary" onclick="simulateIncident()">Simulate</button>
        <ul id="incidents"></ul>
      </article>
      <article class="panel">
        <h2>Runbook Search</h2>
        <p class="muted">Lexical RAG only. No S3 Vectors or OpenAI calls.</p>
        <button onclick="searchRunbooks()">Search thermal</button>
        <pre id="rag"></pre>
      </article>
    </section>
  </main>
  <script>
    async function request(path, options) {
      const response = await fetch(path, { headers: { "content-type": "application/json" }, ...options });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }
    async function check() {
      try {
        await request("/health");
        document.getElementById("status").textContent = "Online";
        await loadIncidents();
      } catch (error) {
        document.getElementById("status").textContent = "Offline";
      }
    }
    async function loadIncidents() {
      const incidents = await request("/v1/incidents");
      document.getElementById("incidents").innerHTML = incidents.map((item) =>
        `<li><strong>${item.device_id}</strong>: ${item.summary}<br><span class="muted">${item.status} · ${Math.round(item.confidence_score * 100)}%</span></li>`
      ).join("");
    }
    async function simulateIncident() {
      await request("/v1/orchestrate/event", {
        method: "POST",
        body: JSON.stringify({
          event_id: `evt_demo_${Date.now()}`,
          fleet_id: "fleet-demo",
          device_id: "robot-07",
          timestamp: new Date().toISOString(),
          metric: "motor_current_a",
          value: 42.5,
          threshold: 35,
          severity: "medium",
          tags: ["motor", "current"]
        })
      });
      await loadIncidents();
    }
    async function searchRunbooks() {
      const hits = await request("/v1/rag/search?query=battery%20thermal&limit=3");
      document.getElementById("rag").textContent = JSON.stringify(hits, null, 2);
    }
    check();
  </script>
</body>
</html>
"""


def _make_lifespan(dependencies):  # type: ignore[no-untyped-def]
    """Return an asynccontextmanager lifespan that starts/stops background tasks."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
        sweep_interval = dependencies.settings.audit_retention_sweep_interval_seconds
        task: asyncio.Task | None = None

        if sweep_interval > 0:
            dependencies.logger.info(
                "Audit retention sweep enabled (interval=%ds)", sweep_interval
            )

            async def _sweep_loop() -> None:
                logger = logging.getLogger("fleet.retention")
                while True:
                    await asyncio.sleep(sweep_interval)
                    try:
                        result = dependencies.repository.purge_expired_audit_events()
                        logger.info(
                            "Audit retention sweep complete: %s",
                            result,
                            extra={"event": "audit_retention_sweep", **result},
                        )
                        dependencies.metrics.increment("audit_retention_sweeps_total")
                        dependencies.metrics.set_gauge(
                            "audit_events_deleted_last_sweep",
                            result.get("audit_events_deleted", 0),
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Audit retention sweep failed: %s", exc)

            task = asyncio.create_task(_sweep_loop())
        else:
            dependencies.logger.info(
                "Audit retention sweep disabled (AUDIT_RETENTION_SWEEP_INTERVAL_SECONDS=0)"
            )

        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    return lifespan


def create_app() -> FastAPI:
    dependencies = initialize_dependencies()

    app = FastAPI(
        title=dependencies.settings.api_title,
        version=dependencies.settings.api_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=_make_lifespan(dependencies),
    )

    app.state.dependencies = dependencies

    if dependencies.settings.cors_origins_list:
        dependencies.logger.info(
            "CORS enabled for origins: %s",
            ", ".join(dependencies.settings.cors_origins_list),
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=dependencies.settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(
        DebugLoggingMiddleware,
        enabled=dependencies.settings.log_level.upper() == "DEBUG",
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(AuthContextMiddleware, settings=dependencies.settings)
    app.add_middleware(CorrelationIDMiddleware)

    dependencies.logger.info(
        "Middleware registered: CorrelationID, AuthContext, RequestLogging, DebugLogging"
    )

    @app.get("/", include_in_schema=False)
    async def demo_home() -> HTMLResponse:
        return HTMLResponse(DEMO_HTML)

    @app.exception_handler(OrchestratorError)
    async def orchestrator_error_handler(_: Request, exc: OrchestratorError) -> JSONResponse:
        dependencies.logger.warning("Handled orchestrator error: %s (%s)", exc.error_code, exc.message)
        payload = exc.to_response()
        payload["detail"] = exc.message
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        dependencies.logger.warning("Request validation error: %s", exc.errors())
        return JSONResponse(
            status_code=422,
            content={
                "detail": exc.errors(),
                "error": {
                    "code": "validation_error",
                    "message": "Request payload validation failed.",
                    "details": {"errors": exc.errors()},
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        dependencies.logger.exception("Unhandled internal error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Unexpected server error.",
                }
            },
        )

    app.include_router(router)
    return app


app = create_app()
