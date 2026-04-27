"""Configuration management for Fleet Health Orchestrator.

Uses Pydantic Settings for validation and environment variable parsing.
All configuration is validated on startup, catching misconfigurations early.
"""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseSettings):
    """Configuration for the Fleet Health Orchestrator API.

    All settings are loaded from environment variables with optional defaults.
    Use .env files during development; rely on environment variables in production.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars
    )

    # === API Configuration ===
    api_title: str = Field(
        default="Fleet Health Orchestrator",
        description="OpenAPI title",
        validation_alias=AliasChoices("API_TITLE", "FLEET_API_TITLE"),
    )
    api_version: str = Field(
        default="0.1.0",
        description="API version for OpenAPI docs",
        validation_alias=AliasChoices("API_VERSION", "FLEET_API_VERSION"),
    )

    # === CORS Configuration ===
    cors_origins: str = Field(
        default="",
        description="Comma-separated list of allowed CORS origins (e.g., 'http://localhost:3000,https://example.com')",
        validation_alias=AliasChoices("CORS_ORIGINS", "FLEET_CORS_ORIGINS"),
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        if not self.cors_origins.strip():
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # === Database Configuration ===
    database_url: str = Field(
        default="",
        description="Database connection URL (preferred for PostgreSQL in production)",
        validation_alias=AliasChoices("DATABASE_URL", "FLEET_DATABASE_URL"),
    )
    database_path: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "data" / "fleet_health.db",
        description="Path to SQLite database file",
        validation_alias=AliasChoices("DATABASE_PATH", "FLEET_DB_PATH"),
    )

    @property
    def database_target(self) -> str:
        """Return the active database target for logging and diagnostics."""
        return self.database_url or str(self.database_path)

    # === Retrieval Backend Configuration ===
    retrieval_backend: str = Field(
        default="lexical",
        description="Retrieval backend: 'lexical' or 's3vectors'",
        validation_alias=AliasChoices("RETRIEVAL_BACKEND", "FLEET_RETRIEVAL_BACKEND"),
    )

    # S3 Vectors (optional)
    s3_vectors_bucket: str = Field(
        default="",
        description="S3 Vectors bucket name (required if backend is 's3vectors')",
        validation_alias=AliasChoices("S3_VECTORS_BUCKET", "FLEET_S3_VECTORS_BUCKET"),
    )
    s3_vectors_index: str = Field(
        default="",
        description="S3 Vectors index name (required if backend is 's3vectors')",
        validation_alias=AliasChoices("S3_VECTORS_INDEX", "FLEET_S3_VECTORS_INDEX"),
    )
    s3_vectors_index_arn: str = Field(
        default="",
        description="S3 Vectors index ARN (alternative to bucket/index pair)",
        validation_alias=AliasChoices("S3_VECTORS_INDEX_ARN", "FLEET_S3_VECTORS_INDEX_ARN"),
    )
    s3_vectors_embedding_dimension: int = Field(
        default=384,
        description="Embedding dimension (must match index and embedding model)",
        validation_alias=AliasChoices(
            "S3_VECTORS_EMBEDDING_DIMENSION",
            "FLEET_S3_VECTORS_EMBEDDING_DIM",
        ),
    )
    s3_vectors_query_vector_json: str = Field(
        default="",
        description="Fixed query vector as JSON array (optional, for testing)",
        validation_alias=AliasChoices(
            "S3_VECTORS_QUERY_VECTOR_JSON",
            "FLEET_S3_VECTORS_QUERY_VECTOR_JSON",
        ),
    )

    # === Embedding Configuration ===
    embedding_provider: str = Field(
        default="hash",
        description="Embedding provider: 'hash', 'openai', 'http', or 'sentence_transformers'",
        validation_alias=AliasChoices("EMBEDDING_PROVIDER", "FLEET_EMBEDDING_PROVIDER"),
    )

    # === OpenAI Configuration (optional) ===
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key (required if using OpenAI for embeddings or LLM enrichment)",
        validation_alias=AliasChoices("OPENAI_API_KEY", "FLEET_OPENAI_API_KEY"),
    )

    # === LLM Enrichment (optional) ===
    llm_report_refine_enabled: bool = Field(
        default=False,
        description="Enable LLM-assisted incident summary refinement",
        validation_alias=AliasChoices("LLM_REPORT_REFINE_ENABLED", "FLEET_OPENAI_REPORT_REFINE"),
    )
    llm_diagnosis_enrich_enabled: bool = Field(
        default=False,
        description="Enable LLM-assisted diagnosis hypothesis enrichment",
        validation_alias=AliasChoices("LLM_DIAGNOSIS_ENRICH_ENABLED", "FLEET_OPENAI_DIAGNOSIS_ENRICH"),
    )
    llm_report_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model for report refinement",
        validation_alias=AliasChoices("LLM_REPORT_MODEL", "FLEET_OPENAI_REPORT_MODEL"),
    )
    llm_diagnosis_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model for diagnosis enrichment",
        validation_alias=AliasChoices("LLM_DIAGNOSIS_MODEL", "FLEET_OPENAI_DIAGNOSIS_MODEL"),
    )

    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model for retrieval and indexing",
        validation_alias=AliasChoices("OPENAI_EMBEDDING_MODEL", "FLEET_OPENAI_EMBEDDING_MODEL"),
    )

    # === Logging Configuration ===
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
        validation_alias=AliasChoices("LOG_LEVEL", "FLEET_LOG_LEVEL"),
    )

    @property
    def llm_enabled(self) -> bool:
        """Return whether OpenAI-backed LLM features are available."""
        return bool(self.openai_api_key.strip())

    @property
    def effective_embedding_provider(self) -> str:
        """Prefer OpenAI embeddings when an API key is present and provider is unset/hash."""
        provider = self.embedding_provider.strip().lower()
        if self.llm_enabled and provider in ("", "hash", "deterministic", "pseudo"):
            return "openai"
        return provider or "hash"

    @property
    def effective_llm_report_refine_enabled(self) -> bool:
        """Auto-enable report refinement when OpenAI is configured."""
        return self.llm_report_refine_enabled or self.llm_enabled

    @property
    def effective_llm_diagnosis_enrich_enabled(self) -> bool:
        """Auto-enable diagnosis enrichment when OpenAI is configured."""
        return self.llm_diagnosis_enrich_enabled or self.llm_enabled

    def __str__(self) -> str:
        """Return configuration summary for logging (excluding secrets)."""
        return (
            f"OrchestratorSettings("
            f"database={self.database_target}, "
            f"retrieval_backend={self.retrieval_backend}, "
            f"embedding_provider={self.effective_embedding_provider}, "
            f"log_level={self.log_level}"
            f")"
        )


def get_settings() -> OrchestratorSettings:
    """Get the current configuration.

    This function is a simple factory that returns a new settings instance.
    In production, you might want to cache this to avoid re-parsing environment
    variables on every request.

    Returns:
        OrchestratorSettings: Validated configuration object.

    Raises:
        ValidationError: If any required setting is missing or invalid.
    """
    return OrchestratorSettings()
