from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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


def create_app() -> FastAPI:
    dependencies = initialize_dependencies()

    app = FastAPI(
        title=dependencies.settings.api_title,
        version=dependencies.settings.api_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
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
