"""Pluggable text embeddings for S3 Vectors query and indexing scripts."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from contextlib import nullcontext
from typing import Any

import httpx
from openai import OpenAI

try:
    from openai import trace as openai_trace
except ImportError:  # pragma: no cover - older SDK fallback
    def openai_trace(*_args: object, **_kwargs: object):
        return nullcontext()


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


def hash_embedding(text: str, dimension: int) -> list[float]:
    """Deterministic pseudo-embedding (SHA256 expansion). Matches prior RAG behavior."""
    if dimension <= 0:
        raise ValueError("embedding dimension must be positive")

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    block = digest
    while len(values) < dimension:
        for i in range(0, len(block), 4):
            if len(values) >= dimension:
                break
            chunk = block[i : i + 4].ljust(4, b"\x00")
            u = int.from_bytes(chunk, "big", signed=False) / float(2**32)
            values.append(u * 2.0 - 1.0)
        block = hashlib.sha256(block).digest()
    return values[:dimension]


def _openai_embedding(text: str, *, model: str, api_key: str, dimension: int) -> list[float]:
    with openai_trace("fleet-health.generate-embedding"):
        response = OpenAI(api_key=api_key).embeddings.create(model=model, input=text)
    data = getattr(response, "data", None)
    if not isinstance(data, list) or not data:
        raise RuntimeError("OpenAI embeddings response missing data[]")
    vec = getattr(data[0], "embedding", None)
    if not isinstance(vec, list):
        raise RuntimeError("OpenAI embeddings response missing embedding vector")
    out = [float(x) for x in vec]
    if len(out) != dimension:
        raise RuntimeError(
            f"OpenAI returned dimension {len(out)} but FLEET_S3_VECTORS_EMBEDDING_DIM is {dimension}. "
            "Align the model and index, or set FLEET_S3_VECTORS_EMBEDDING_DIM to the model output size."
        )
    return out


def _http_embedding(text: str, *, url: str, dimension: int) -> list[float]:
    try:
        response = httpx.post(
            url,
            json={"input": text},
            headers={"Content-Type": "application/json"},
            timeout=60.0
        )
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"HTTP embedding request to {url} timed out") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"HTTP embedding request to {url} failed: {exc}") from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _response_error_detail(response)
        message = f"HTTP embedding request to {url} failed with HTTP {response.status_code}"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message) from exc

    payload = response.json()
    vec = payload.get("embedding")
    if not isinstance(vec, list):
        raise RuntimeError(
            "FLEET_EMBEDDING_HTTP_URL response must be JSON with top-level \"embedding\" array."
        )
    out = [float(x) for x in vec]
    if len(out) != dimension:
        raise RuntimeError(
            f"HTTP embedding length {len(out)} does not match FLEET_S3_VECTORS_EMBEDDING_DIM ({dimension})."
        )
    return out


def _sentence_transformer_embedding(text: str, *, model_name: str, dimension: int) -> list[float]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "FLEET_EMBEDDING_PROVIDER=sentence_transformers requires the optional dependency. "
            'Install with: pip install "fleet-health-orchestrator[embeddings]"'
        ) from exc

    model = SentenceTransformer(model_name)
    vec = model.encode(text, convert_to_numpy=True)
    out = [float(x) for x in vec.tolist()]
    if len(out) != dimension:
        raise RuntimeError(
            f"Sentence-transformer model {model_name!r} produced dimension {len(out)}, "
            f"expected {dimension} (set FLEET_S3_VECTORS_EMBEDDING_DIM to match the model)."
        )
    return out


def create_query_embedder(
    dimension: int,
    *,
    provider: str | None = None,
    openai_api_key: str | None = None,
    openai_model: str | None = None,
    http_url: str | None = None,
    sentence_transformer_model: str | None = None
) -> Callable[[str], list[float]]:
    """Factory for ``embed(query_text) -> vector`` used by S3 Vectors search and indexing."""
    raw = provider if provider is not None else os.getenv("FLEET_EMBEDDING_PROVIDER")
    name = (raw or "hash").strip().lower()
    key = openai_api_key if openai_api_key is not None else (
        os.getenv("OPENAI_API_KEY") or os.getenv("FLEET_OPENAI_API_KEY", "")
    )
    oa_model = (
        openai_model
        if openai_model is not None
        else os.getenv("OPENAI_EMBEDDING_MODEL")
        or os.getenv("FLEET_OPENAI_EMBEDDING_MODEL")
        or "text-embedding-3-large"
    )
    st_model = (
        sentence_transformer_model
        if sentence_transformer_model is not None
        else os.getenv("FLEET_SENTENCE_TRANSFORMER_MODEL", "all-MiniLM-L6-v2")
    )
    url = http_url if http_url is not None else (os.getenv("FLEET_EMBEDDING_HTTP_URL") or "")

    if name in ("hash", "deterministic", "pseudo", ""):
        return lambda q: hash_embedding(q, dimension)

    if name == "openai":
        if not key.strip():
            raise ValueError("FLEET_EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY.")
        return lambda q: _openai_embedding(q, model=oa_model, api_key=key.strip(), dimension=dimension)

    if name in ("http", "http_json"):
        if not url.strip():
            raise ValueError("FLEET_EMBEDDING_PROVIDER=http requires FLEET_EMBEDDING_HTTP_URL.")
        u = url.strip()
        return lambda q: _http_embedding(q, url=u, dimension=dimension)

    if name in ("sentence_transformers", "sentence-transformers", "st"):
        mn = st_model.strip()
        return lambda q: _sentence_transformer_embedding(q, model_name=mn, dimension=dimension)

    raise ValueError(
        f"Unsupported FLEET_EMBEDDING_PROVIDER={name!r}. "
        "Use hash, openai, http, or sentence_transformers."
    )


def embed_document_for_index(
    document: dict[str, object],
    embed: Callable[[str], list[float]]
) -> tuple[str, dict[str, Any]]:
    """Build S3 Vectors index key and metadata for ``put_vectors`` from a RAG document dict."""
    doc_id = str(document["document_id"])
    title = str(document.get("title", ""))
    content = str(document.get("content", ""))
    source = str(document.get("source", "manual"))
    text = f"{title}\n{content}".strip() or doc_id
    excerpt = content[:500] if content else title[:500]
    metadata = {
        "document_id": doc_id,
        "title": title,
        "source": source,
        "excerpt": excerpt
    }
    vector = embed(text)
    row: dict[str, Any] = {
        "key": doc_id,
        "data": {"float32": vector},
        "metadata": metadata
    }
    return doc_id, row
