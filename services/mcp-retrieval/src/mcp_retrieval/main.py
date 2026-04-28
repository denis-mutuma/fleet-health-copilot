"""MCP tools for retrieval and RAG context lookup.

This module exposes a small MCP server that proxies retrieval requests to the
orchestrator RAG API. The tool contract intentionally returns a stable,
JSON-serializable shape consumed by downstream agent steps.
"""

import os
from typing import Any

import httpx

DEFAULT_ORCHESTRATOR_URL = "http://127.0.0.1:8000"
RAG_SEARCH_PATH = "/v1/rag/search"
REQUEST_TIMEOUT_SECONDS = 10.0


def _response_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except Exception:
        return None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return None


def _request_json(
    *,
    operation: str,
    request_fn: Any,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    try:
        response = request_fn(url, **kwargs)
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"{operation} request to {url} timed out") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"{operation} request to {url} failed: {exc}") from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _response_error_detail(response)
        message = f"{operation} request to {url} failed with HTTP {response.status_code}"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message) from exc
    return response


def _orchestrator_base_url() -> str:
    """Resolve orchestrator base URL from env with a safe local default.

    Environment variable:
    - ORCHESTRATOR_API_BASE_URL: Optional absolute URL for the orchestrator API.
    """
    return os.getenv("ORCHESTRATOR_API_BASE_URL", DEFAULT_ORCHESTRATOR_URL)


def retrieve_supporting_context(
    query: str, base_url: str = DEFAULT_ORCHESTRATOR_URL, limit: int = 5
) -> dict[str, Any]:
    """Query orchestrator RAG search and return a normalized retrieval payload.

    Args:
        query: Natural-language retrieval query from an upstream agent/tool.
        base_url: Orchestrator base URL (no trailing slash required).
        limit: Maximum number of hits requested from orchestrator.

    Returns:
        A stable object with the original ``query`` and orchestrator ``hits``.

    Raises:
        httpx.HTTPStatusError: If orchestrator returns a non-2xx response.
        httpx.RequestError: If the request cannot be completed.
    """
    response = _request_json(
        operation="retrieve_supporting_context",
        request_fn=httpx.get,
        url=f"{base_url.rstrip('/')}{RAG_SEARCH_PATH}",
        params={"query": query, "limit": limit},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return {"query": query, "hits": response.json()}


def create_mcp_server() -> Any:
    """Create and register MCP tools for retrieval workflows.

    Returns:
        FastMCP server instance with retrieval tools registered.

    Raises:
        RuntimeError: If the MCP runtime dependency is unavailable.
    """
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
        """Search runbooks and incident history via the orchestrator RAG API.

        The returned structure is intentionally thin and deterministic so MCP
        callers can compose retrieval output without additional adaptation.
        """
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
