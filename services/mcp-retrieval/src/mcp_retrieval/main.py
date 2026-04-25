from typing import Any

import httpx


def retrieve_supporting_context(
    query: str, base_url: str = "http://127.0.0.1:8000", limit: int = 5
) -> dict[str, Any]:
    response = httpx.get(
        f"{base_url}/v1/rag/search",
        params={"query": query, "limit": limit},
        timeout=10.0
    )
    response.raise_for_status()
    return {"query": query, "hits": response.json()}
