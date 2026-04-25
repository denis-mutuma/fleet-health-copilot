from collections import Counter
from re import findall

from fleet_health_orchestrator.models import RetrievalHit


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in findall(r"[a-zA-Z0-9_]+", text)]


def rank_documents(
    query: str, documents: list[dict[str, object]], limit: int = 5
) -> list[RetrievalHit]:
    query_counts = Counter(_tokenize(query))
    hits: list[RetrievalHit] = []

    for document in documents:
        content = str(document["content"])
        content_counts = Counter(_tokenize(content))
        score = float(sum(query_counts[token] * content_counts[token] for token in query_counts))
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
