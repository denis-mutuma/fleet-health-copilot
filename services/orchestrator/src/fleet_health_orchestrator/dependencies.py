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
from fleet_health_orchestrator.config import OrchestratorSettings, get_settings
from fleet_health_orchestrator.exceptions import DependencyInitializationError
from fleet_health_orchestrator.logging_config import setup_logging
from fleet_health_orchestrator.rag import RetrievalBackend, build_retrieval_backend
from fleet_health_orchestrator.repository import FleetRepository


@dataclass
class AppDependencies:
    settings: OrchestratorSettings
    logger: logging.Logger
    repository: FleetRepository
    retrieval_backend: RetrievalBackend
    orchestrator: AgentOrchestrator
    metrics: dict[str, float]


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
        repository = FleetRepository(settings.database_path)
        logger.info("Repository initialized at %s", settings.database_path)
    except Exception as exc:
        error = DependencyInitializationError(
            "Failed to initialize repository.",
            details={"database_path": str(settings.database_path)},
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
            embedding_provider=settings.embedding_provider,
        )
        logger.info("Retrieval backend initialized: %s", settings.retrieval_backend)

        if settings.retrieval_backend.lower() == "s3vectors" and settings.embedding_provider.lower() in (
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

    metrics = {
        "events_ingested_total": 0.0,
        "incidents_generated_total": 0.0,
        "rag_queries_total": 0.0,
        "rag_query_latency_ms_last": 0.0,
        "orchestration_latency_ms_last": 0.0,
    }

    return AppDependencies(
        settings=settings,
        logger=logger,
        repository=repository,
        retrieval_backend=retrieval_backend,
        orchestrator=orchestrator,
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
