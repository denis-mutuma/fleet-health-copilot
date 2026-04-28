import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from pydantic import ValidationError

from fleet_health_orchestrator.agents import (
    AgentOrchestrator,
    DiagnosisAgent,
    MonitorAgent,
    PlannerAgent,
    ReporterAgent,
    RetrieverAgent,
    VerifierAgent,
)
from fleet_health_orchestrator.auth_context import RequestIdentity, anonymous_identity
from fleet_health_orchestrator.config import OrchestratorSettings, get_settings
from fleet_health_orchestrator.exceptions import AuthorizationError, DependencyInitializationError
from fleet_health_orchestrator.chat_orchestrator import ChatToolOrchestrator
from fleet_health_orchestrator.logging_config import setup_logging
from fleet_health_orchestrator.mcp_client_adapter import MCPClientAdapter
from fleet_health_orchestrator.metrics import RuntimeMetrics
from fleet_health_orchestrator.rag import RetrievalBackend, build_retrieval_backend
from fleet_health_orchestrator.repository import FleetRepository


@dataclass
class AppDependencies:
    settings: OrchestratorSettings
    logger: logging.Logger
    repository: FleetRepository
    retrieval_backend: RetrievalBackend
    orchestrator: AgentOrchestrator
    mcp_adapter: MCPClientAdapter | None
    chat_orchestrator: ChatToolOrchestrator | None
    metrics: RuntimeMetrics


def initialize_dependencies() -> AppDependencies:
    """Build and validate all runtime dependencies for the API process."""
    try:
        settings = get_settings()
    except ValidationError as exc:
        raise RuntimeError(
            f"Configuration validation failed. Check your environment variables and .env file.\\n{exc}"
        ) from exc

    logger = setup_logging(log_level=settings.log_level)

    try:
        repository = FleetRepository(settings.database_path, database_url=settings.database_url)
        logger.info("Repository initialized at %s", settings.database_target)
    except Exception as exc:
        error = DependencyInitializationError(
            "Failed to initialize repository.",
            details={"database": settings.database_target},
        )
        logger.error("%s %s", error.message, exc)
        raise RuntimeError(error.message) from exc

    try:
        retrieval_backend = build_retrieval_backend(
            backend_name=settings.retrieval_backend,
            s3_vectors_bucket=settings.s3_vectors_bucket,
            s3_vectors_index=settings.s3_vectors_index,
            s3_vectors_index_arn=settings.s3_vectors_index_arn,
            s3_vectors_embedding_dimension=settings.s3_vectors_embedding_dimension,
            s3_vectors_query_vector_json=settings.s3_vectors_query_vector_json,
            embedding_provider=settings.effective_embedding_provider,
        )
        logger.info(
            "Retrieval backend initialized: %s (embedding provider: %s)",
            settings.retrieval_backend,
            settings.effective_embedding_provider,
        )

        if settings.retrieval_backend.lower() == "s3vectors" and settings.effective_embedding_provider.lower() in (
            "hash",
            "deterministic",
            "pseudo",
            "",
        ):
            logger.warning(
                "Using s3vectors backend with hash-style embeddings. "
                "ANN quality is not production-like. "
                "Use 'openai', 'http', or 'sentence_transformers' and ensure "
                "EMBEDDING_DIMENSION matches the model output."
            )
    except Exception as exc:
        error = DependencyInitializationError(
            "Failed to initialize retrieval backend.",
            details={"retrieval_backend": settings.retrieval_backend},
        )
        logger.error("%s %s", error.message, exc)
        raise RuntimeError(error.message) from exc

    try:
        orchestrator = AgentOrchestrator(
            monitor=MonitorAgent(),
            retriever=RetrieverAgent(retrieval_backend=retrieval_backend),
            diagnosis=DiagnosisAgent(),
            planner=PlannerAgent(),
            verifier=VerifierAgent(),
            reporter=ReporterAgent(),
        )
        logger.info("Agent orchestrator initialized")
    except Exception as exc:
        error = DependencyInitializationError("Failed to initialize agent orchestrator.")
        logger.error("%s %s", error.message, exc)
        raise RuntimeError(error.message) from exc

    mcp_adapter: MCPClientAdapter | None = None
    chat_orchestrator: ChatToolOrchestrator | None = None
    try:
        mcp_adapter = MCPClientAdapter(
            repository=repository,
            retrieval_backend=retrieval_backend,
            logger=logger,
            tool_timeout_seconds=settings.chat_tool_timeout_seconds,
            transport=settings.chat_tool_transport,
            retrieval_base_url=settings.chat_tool_http_retrieval_base_url,
            incidents_base_url=settings.chat_tool_http_incidents_base_url,
            telemetry_base_url=settings.chat_tool_http_telemetry_base_url,
        )
        chat_orchestrator = ChatToolOrchestrator(
            logger=logger,
            settings=settings,
            mcp_adapter=mcp_adapter,
        )
        logger.info("Chat tool orchestrator initialized")
    except Exception as exc:
        logger.warning("Chat tool orchestrator initialization failed; deterministic fallback remains active: %s", exc)

    metrics = RuntimeMetrics()

    return AppDependencies(
        settings=settings,
        logger=logger,
        repository=repository,
        retrieval_backend=retrieval_backend,
        orchestrator=orchestrator,
        mcp_adapter=mcp_adapter,
        chat_orchestrator=chat_orchestrator,
        metrics=metrics,
    )


def get_dependencies(request: Request) -> AppDependencies:
    dependencies = getattr(request.app.state, "dependencies", None)
    if dependencies is None:
        raise RuntimeError("App dependencies are not initialized.")
    return dependencies


def get_logger(request: Request) -> logging.Logger:
    dependencies = get_dependencies(request)
    return dependencies.logger


def get_request_identity(request: Request) -> RequestIdentity:
    identity = getattr(request.state, "identity", None)
    if identity is None:
        return anonymous_identity()
    return identity


def require_any_role(request: Request, expected_roles: list[str]) -> RequestIdentity:
    identity = get_request_identity(request)
    if not identity.has_any_role(expected_roles):
        raise AuthorizationError(
            "Caller does not have the required role.",
            details={
                "required_roles": expected_roles,
                "provided_roles": sorted(identity.roles),
            },
        )
    return identity


def require_mutation_access(request: Request) -> RequestIdentity:
    dependencies = get_dependencies(request)
    return require_any_role(request, dependencies.settings.auth_mutation_roles_list)
