import json
from collections import Counter
from collections.abc import Callable
from re import findall
from typing import Any, Protocol

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from fleet_health_orchestrator.embeddings import create_query_embedder, hash_embedding
from fleet_health_orchestrator.models import RetrievalHit


class RetrievalBackend(Protocol):
    def search(
        self,
        query: str,
        documents: list[dict[str, object]],
        limit: int = 5
    ) -> list[RetrievalHit]:
        ...


class LexicalRetrievalBackend:
    name = "lexical"

    def search(
        self,
        query: str,
        documents: list[dict[str, object]],
        limit: int = 5
    ) -> list[RetrievalHit]:
        query_counts = Counter(_tokenize(query))
        hits: list[RetrievalHit] = []

        for document in documents:
            content = str(document["content"])
            content_counts = Counter(_tokenize(content))
            score = float(
                sum(query_counts[token] * content_counts[token] for token in query_counts)
            )
            if score <= 0:
                continue
            hits.append(
                RetrievalHit(
                    document_id=str(document["document_id"]),
                    source=str(document["source"]),
                    title=str(document["title"]),
                    score=score,
                    excerpt=content[:240]
                )
            )

        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]


class S3VectorsRetrievalBackend:
    """RAG retrieval via Amazon S3 Vectors ``query_vectors`` (boto3 ``s3vectors`` client)."""

    name = "s3vectors"

    def __init__(
        self,
        bucket_name: str,
        index_name: str,
        *,
        index_arn: str | None = None,
        embedding_dimension: int = 384,
        fixed_query_vector: list[float] | None = None,
        embed_query: Callable[[str], list[float]] | None = None,
        client: Any | None = None
    ) -> None:
        self.bucket_name = bucket_name
        self.index_name = index_name
        self.index_arn = (index_arn or "").strip() or None
        self.embedding_dimension = embedding_dimension
        self._fixed_query_vector = fixed_query_vector
        self._embed_query = embed_query
        self._client = client

    def search(
        self,
        query: str,
        documents: list[dict[str, object]],
        limit: int = 5
    ) -> list[RetrievalHit]:
        if limit <= 0:
            return []

        lookup = _document_lookup(documents)
        if self._fixed_query_vector is not None:
            vector = self._fixed_query_vector
        elif self._embed_query is not None:
            vector = self._embed_query(query)
        else:
            vector = hash_embedding(query, self.embedding_dimension)

        params: dict[str, Any] = {
            "topK": limit,
            "queryVector": {"float32": vector},
            "returnMetadata": True,
            "returnDistance": True
        }
        if self.index_arn:
            params["indexArn"] = self.index_arn
        else:
            params["vectorBucketName"] = self.bucket_name
            params["indexName"] = self.index_name

        client = self._client if self._client is not None else boto3.client("s3vectors")
        try:
            response = client.query_vectors(**params)
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(
                "S3 Vectors query failed. Check credentials, IAM (s3vectors:QueryVectors "
                "and s3vectors:GetVectors when returnMetadata is true), bucket/index or ARN, "
                "and that FLEET_S3_VECTORS_EMBEDDING_DIM matches the index dimension."
            ) from exc

        vectors = response.get("vectors") or []
        distance_metric = response.get("distanceMetric") or ""

        hits: list[RetrievalHit] = []
        for row in vectors:
            if not isinstance(row, dict):
                continue
            key = str(row.get("key") or "")
            meta_raw = row.get("metadata")
            meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}

            doc_id = str(meta.get("document_id") or meta.get("documentId") or key or "")
            if not doc_id:
                continue

            corpus = lookup.get(doc_id, {})
            title = str(meta.get("title") or corpus.get("title") or doc_id)
            source = str(meta.get("source") or corpus.get("source") or "manual")
            excerpt_src = meta.get("excerpt") or corpus.get("content") or ""
            excerpt = str(excerpt_src)[:240]

            distance = row.get("distance")
            score = _distance_to_score(distance, distance_metric)

            hits.append(
                RetrievalHit(
                    document_id=doc_id,
                    source=source,
                    title=title,
                    score=score,
                    excerpt=excerpt
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]


def build_retrieval_backend(
    backend_name: str | None = None,
    s3_vectors_bucket: str | None = None,
    s3_vectors_index: str | None = None,
    s3_vectors_index_arn: str | None = None,
    s3_vectors_embedding_dimension: int | None = None,
    s3_vectors_query_vector_json: str | None = None,
    embedding_provider: str | None = None
) -> RetrievalBackend:
    normalized_name = (backend_name or "lexical").strip().lower()

    if normalized_name == "lexical":
        return LexicalRetrievalBackend()

    if normalized_name == "s3vectors":
        bucket = (s3_vectors_bucket or "").strip()
        index = (s3_vectors_index or "").strip()
        arn = (s3_vectors_index_arn or "").strip()
        has_pair = bool(bucket and index)
        has_arn = bool(arn)
        if not has_pair and not has_arn:
            raise ValueError(
                "For FLEET_RETRIEVAL_BACKEND=s3vectors, set FLEET_S3_VECTORS_BUCKET and "
                "FLEET_S3_VECTORS_INDEX, or set FLEET_S3_VECTORS_INDEX_ARN."
            )

        dimension = int(s3_vectors_embedding_dimension or 384)
        fixed_vec = _parse_fixed_query_vector_json(
            s3_vectors_query_vector_json,
            expected_dim=dimension
        )

        embed_query = (
            None
            if fixed_vec is not None
            else create_query_embedder(dimension, provider=embedding_provider)
        )

        return S3VectorsRetrievalBackend(
            bucket_name=bucket,
            index_name=index,
            index_arn=arn or None,
            embedding_dimension=dimension,
            fixed_query_vector=fixed_vec,
            embed_query=embed_query
        )

    raise ValueError(
        f"Unsupported retrieval backend '{backend_name}'. "
        "Expected 'lexical' or 's3vectors'."
    )


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in findall(r"[a-zA-Z0-9_]+", text)]


def _document_lookup(documents: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for document in documents:
        doc_id = str(document.get("document_id", ""))
        if doc_id:
            out[doc_id] = document
    return out


def _parse_fixed_query_vector_json(
    raw: str | None,
    *,
    expected_dim: int
) -> list[float] | None:
    if raw is None or not str(raw).strip():
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("FLEET_S3_VECTORS_QUERY_VECTOR_JSON must be a JSON array of numbers.")
    vector = [float(x) for x in parsed]
    if len(vector) != expected_dim:
        raise ValueError(
            f"FLEET_S3_VECTORS_QUERY_VECTOR_JSON length {len(vector)} does not match "
            f"FLEET_S3_VECTORS_EMBEDDING_DIM ({expected_dim})."
        )
    return vector


def _distance_to_score(distance: object, distance_metric: str) -> float:
    if distance is None:
        return 0.0
    try:
        d = float(distance)
    except (TypeError, ValueError):
        return 0.0
    metric = (distance_metric or "").lower()
    if metric == "cosine":
        return max(0.0, 1.0 - d)
    return 1.0 / (1.0 + max(0.0, d))


def rank_documents(
    query: str, documents: list[dict[str, object]], limit: int = 5
) -> list[RetrievalHit]:
    return LexicalRetrievalBackend().search(
        query=query,
        documents=documents,
        limit=limit
    )
