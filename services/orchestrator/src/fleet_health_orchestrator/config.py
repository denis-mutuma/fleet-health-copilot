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
        default=3072,
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

    llm_chat_enabled: bool = Field(
        default=False,
        description="Enable OpenAI-generated chat responses with tool execution",
        validation_alias=AliasChoices("LLM_CHAT_ENABLED", "FLEET_LLM_CHAT_ENABLED"),
    )
    llm_chat_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model for chat response generation",
        validation_alias=AliasChoices("LLM_CHAT_MODEL", "FLEET_LLM_CHAT_MODEL"),
    )
    llm_chat_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for chat generation",
        validation_alias=AliasChoices("LLM_CHAT_TEMPERATURE", "FLEET_LLM_CHAT_TEMPERATURE"),
    )
    llm_chat_max_output_tokens: int = Field(
        default=600,
        ge=64,
        le=4096,
        description="Maximum output tokens for OpenAI chat responses",
        validation_alias=AliasChoices("LLM_CHAT_MAX_OUTPUT_TOKENS", "FLEET_LLM_CHAT_MAX_OUTPUT_TOKENS"),
    )
    chat_tool_timeout_seconds: float = Field(
        default=8.0,
        ge=1.0,
        le=60.0,
        description="Timeout for each MCP tool call during chat (seconds)",
        validation_alias=AliasChoices("CHAT_TOOL_TIMEOUT_SECONDS", "FLEET_CHAT_TOOL_TIMEOUT_SECONDS"),
    )
    chat_tool_transport: str = Field(
        default="local",
        description="Chat tool transport: local or http_json",
        validation_alias=AliasChoices("CHAT_TOOL_TRANSPORT", "FLEET_CHAT_TOOL_TRANSPORT"),
    )
    chat_tool_http_retrieval_base_url: str = Field(
        default="http://127.0.0.1:8000",
        description="Base URL for retrieval HTTP JSON tool transport",
        validation_alias=AliasChoices(
            "CHAT_TOOL_HTTP_RETRIEVAL_BASE_URL",
            "FLEET_CHAT_TOOL_HTTP_RETRIEVAL_BASE_URL",
        ),
    )
    chat_tool_http_incidents_base_url: str = Field(
        default="http://127.0.0.1:8000",
        description="Base URL for incidents HTTP JSON tool transport",
        validation_alias=AliasChoices(
            "CHAT_TOOL_HTTP_INCIDENTS_BASE_URL",
            "FLEET_CHAT_TOOL_HTTP_INCIDENTS_BASE_URL",
        ),
    )
    chat_tool_http_telemetry_base_url: str = Field(
        default="http://127.0.0.1:8000",
        description="Base URL for telemetry HTTP JSON tool transport",
        validation_alias=AliasChoices(
            "CHAT_TOOL_HTTP_TELEMETRY_BASE_URL",
            "FLEET_CHAT_TOOL_HTTP_TELEMETRY_BASE_URL",
        ),
    )
    chat_tool_max_calls_per_turn: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Maximum MCP tool calls allowed per chat turn",
        validation_alias=AliasChoices("CHAT_TOOL_MAX_CALLS_PER_TURN", "FLEET_CHAT_TOOL_MAX_CALLS_PER_TURN"),
    )
    llm_chat_input_cost_per_1k_tokens_usd: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="Input token price in USD per 1K tokens for chat cost estimation",
        validation_alias=AliasChoices(
            "LLM_CHAT_INPUT_COST_PER_1K_TOKENS_USD",
            "FLEET_LLM_CHAT_INPUT_COST_PER_1K_TOKENS_USD",
        ),
    )
    llm_chat_output_cost_per_1k_tokens_usd: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="Output token price in USD per 1K tokens for chat cost estimation",
        validation_alias=AliasChoices(
            "LLM_CHAT_OUTPUT_COST_PER_1K_TOKENS_USD",
            "FLEET_LLM_CHAT_OUTPUT_COST_PER_1K_TOKENS_USD",
        ),
    )
    llm_chat_max_turn_cost_usd: float = Field(
        default=0.0,
        ge=0.0,
        le=50.0,
        description="Maximum estimated USD cost allowed for a single chat turn (0 disables cap)",
        validation_alias=AliasChoices(
            "LLM_CHAT_MAX_TURN_COST_USD",
            "FLEET_LLM_CHAT_MAX_TURN_COST_USD",
        ),
    )

    openai_embedding_model: str = Field(
        default="text-embedding-3-large",
        description="OpenAI embedding model for retrieval and indexing",
        validation_alias=AliasChoices("OPENAI_EMBEDDING_MODEL", "FLEET_OPENAI_EMBEDDING_MODEL"),
    )

    # === RAG Ingestion ===
    rag_chunk_size_chars: int = Field(
        default=1200,
        ge=200,
        le=20000,
        description="Default chunk size for uploaded RAG documents (characters).",
        validation_alias=AliasChoices("RAG_CHUNK_SIZE_CHARS", "FLEET_RAG_CHUNK_SIZE_CHARS"),
    )
    rag_chunk_overlap_chars: int = Field(
        default=200,
        ge=0,
        le=5000,
        description="Chunk overlap for uploaded RAG documents (characters).",
        validation_alias=AliasChoices("RAG_CHUNK_OVERLAP_CHARS", "FLEET_RAG_CHUNK_OVERLAP_CHARS"),
    )
    rag_upload_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        le=100 * 1024 * 1024,
        description="Maximum document upload size in bytes.",
        validation_alias=AliasChoices("RAG_UPLOAD_MAX_BYTES", "FLEET_RAG_UPLOAD_MAX_BYTES"),
    )
    rag_index_batch_size: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Max chunk vectors per S3 Vectors put_vectors call.",
        validation_alias=AliasChoices("RAG_INDEX_BATCH_SIZE", "FLEET_RAG_INDEX_BATCH_SIZE"),
    )

    # === Logging Configuration ===
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
        validation_alias=AliasChoices("LOG_LEVEL", "FLEET_LOG_LEVEL"),
    )

    # === Request Identity and Authorization Configuration ===
    auth_required: bool = Field(
        default=False,
        description="Require authenticated identity headers on all requests.",
        validation_alias=AliasChoices("AUTH_REQUIRED", "FLEET_AUTH_REQUIRED"),
    )
    auth_enforce_tenant_scope: bool = Field(
        default=False,
        description="Require tenant header when authentication is required.",
        validation_alias=AliasChoices("AUTH_ENFORCE_TENANT_SCOPE", "FLEET_AUTH_ENFORCE_TENANT_SCOPE"),
    )
    auth_actor_header: str = Field(
        default="x-actor-id",
        description="Header carrying authenticated actor identity.",
        validation_alias=AliasChoices("AUTH_ACTOR_HEADER", "FLEET_AUTH_ACTOR_HEADER"),
    )
    auth_tenant_header: str = Field(
        default="x-tenant-id",
        description="Header carrying tenant identifier.",
        validation_alias=AliasChoices("AUTH_TENANT_HEADER", "FLEET_AUTH_TENANT_HEADER"),
    )
    auth_fleet_header: str = Field(
        default="x-fleet-id",
        description="Header carrying fleet identifier.",
        validation_alias=AliasChoices("AUTH_FLEET_HEADER", "FLEET_AUTH_FLEET_HEADER"),
    )
    auth_roles_header: str = Field(
        default="x-roles",
        description="Comma-separated roles header.",
        validation_alias=AliasChoices("AUTH_ROLES_HEADER", "FLEET_AUTH_ROLES_HEADER"),
    )
    auth_provider_header: str = Field(
        default="x-auth-provider",
        description="Header carrying auth provider identifier.",
        validation_alias=AliasChoices("AUTH_PROVIDER_HEADER", "FLEET_AUTH_PROVIDER_HEADER"),
    )
    auth_default_roles: str = Field(
        default="operator",
        description="Default roles applied when role header is absent.",
        validation_alias=AliasChoices("AUTH_DEFAULT_ROLES", "FLEET_AUTH_DEFAULT_ROLES"),
    )
    auth_mutation_roles: str = Field(
        default="operator,admin",
        description="Roles allowed for mutating endpoints.",
        validation_alias=AliasChoices("AUTH_MUTATION_ROLES", "FLEET_AUTH_MUTATION_ROLES"),
    )

    # === Audit Retention ===
    audit_retention_sweep_interval_seconds: int = Field(
        default=0,
        ge=0,
        description=(
            "How often (in seconds) the background retention sweep runs. "
            "0 disables the background sweep entirely. "
            "Recommended production value: 86400 (once per day)."
        ),
        validation_alias=AliasChoices(
            "AUDIT_RETENTION_SWEEP_INTERVAL_SECONDS",
            "FLEET_AUDIT_RETENTION_SWEEP_INTERVAL_SECONDS",
        ),
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

    @property
    def effective_llm_chat_enabled(self) -> bool:
        """Auto-enable chat LLM mode when OpenAI is configured."""
        return self.llm_chat_enabled or self.llm_enabled

    def __str__(self) -> str:
        """Return configuration summary for logging (excluding secrets)."""
        return (
            f"OrchestratorSettings("
            f"database={self.database_target}, "
            f"retrieval_backend={self.retrieval_backend}, "
            f"embedding_provider={self.effective_embedding_provider}, "
            f"auth_required={self.auth_required}, "
            f"log_level={self.log_level}"
            f")"
        )

    @property
    def auth_default_roles_list(self) -> list[str]:
        return [
            role.strip().lower()
            for role in self.auth_default_roles.split(",")
            if role.strip()
        ]

    @property
    def auth_mutation_roles_list(self) -> list[str]:
        return [
            role.strip().lower()
            for role in self.auth_mutation_roles.split(",")
            if role.strip()
        ]


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
