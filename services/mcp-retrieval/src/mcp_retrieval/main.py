"""MCP tools for retrieval and RAG context lookup."""

import os
from typing import Any

import httpx

DEFAULT_ORCHESTRATOR_URL = "http://127.0.0.1:8000"


def _orchestrator_base_url() -> str:
    """Resolve orchestrator base URL from env with a safe local default."""
    return os.getenv("ORCHESTRATOR_API_BASE_URL", DEFAULT_ORCHESTRATOR_URL)


def retrieve_supporting_context(
    query: str, base_url: str = DEFAULT_ORCHESTRATOR_URL, limit: int = 5
) -> dict[str, Any]:
    """Run retrieval against orchestrator RAG search and return normalized shape."""
    response = httpx.get(
        f"{base_url.rstrip('/')}/v1/rag/search",
        params={"query": query, "limit": limit},
        timeout=10.0
    )
    response.raise_for_status()
    return {"query": query, "hits": response.json()}


def create_mcp_server() -> Any:
    """Create and register MCP tools for retrieval workflows."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            "The MCP runtime is not installed. Install the mcp-retrieval package "
            "with its MCP dependency before starting the server."
        ) from error

    server = FastMCP("fleet-health-retrieval")

    @server.tool()
    def search_operational_context(query: str, limit: int = 5) -> dict[str, Any]:
        """Search runbooks and incident history through the orchestrator RAG API."""
        return retrieve_supporting_context(
            query=query,
            base_url=_orchestrator_base_url(),
            limit=limit
        )

    return server


def run_server() -> None:
    """Entrypoint used by the package script (`mcp-retrieval`)."""
    create_mcp_server().run()


if __name__ == "__main__":
    run_server()
