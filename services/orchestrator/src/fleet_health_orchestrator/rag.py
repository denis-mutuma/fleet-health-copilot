from collections import Counter
from re import findall
from typing import Protocol

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
    name = "s3vectors"

    def __init__(self, bucket_name: str, index_name: str) -> None:
        self.bucket_name = bucket_name
        self.index_name = index_name

    def search(
        self,
        query: str,
        documents: list[dict[str, object]],
        limit: int = 5
    ) -> list[RetrievalHit]:
        raise NotImplementedError(
            "S3 Vectors retrieval is configured but not implemented yet. "
            "Use FLEET_RETRIEVAL_BACKEND=lexical for local development."
        )


def build_retrieval_backend(
    backend_name: str | None = None,
    s3_vectors_bucket: str | None = None,
    s3_vectors_index: str | None = None
) -> RetrievalBackend:
    normalized_name = (backend_name or "lexical").strip().lower()

    if normalized_name == "lexical":
        return LexicalRetrievalBackend()

    if normalized_name == "s3vectors":
        if not s3_vectors_bucket or not s3_vectors_index:
            raise ValueError(
                "FLEET_S3_VECTORS_BUCKET and FLEET_S3_VECTORS_INDEX are required "
                "when FLEET_RETRIEVAL_BACKEND=s3vectors."
            )
        return S3VectorsRetrievalBackend(
            bucket_name=s3_vectors_bucket,
            index_name=s3_vectors_index
        )

    raise ValueError(
        f"Unsupported retrieval backend '{backend_name}'. "
        "Expected 'lexical' or 's3vectors'."
    )


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in findall(r"[a-zA-Z0-9_]+", text)]


def rank_documents(
    query: str, documents: list[dict[str, object]], limit: int = 5
) -> list[RetrievalHit]:
    return LexicalRetrievalBackend().search(
        query=query,
        documents=documents,
        limit=limit
    )
