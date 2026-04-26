#!/usr/bin/env python3
"""Upsert RAG documents from SQLite into an Amazon S3 Vectors index (put_vectors)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Allow running as `python scripts/index_s3_vectors.py` from repo root
_ORCH_SRC = Path(__file__).resolve().parents[1] / "src"
if _ORCH_SRC.is_dir():
    sys.path.insert(0, str(_ORCH_SRC))

from fleet_health_orchestrator.embeddings import (  # noqa: E402
    create_query_embedder,
    embed_document_for_index,
)
from fleet_health_orchestrator.repository import FleetRepository  # noqa: E402


def _put_batch(
    client: object,
    *,
    bucket: str,
    index: str,
    index_arn: str | None,
    vectors: list[dict[str, object]]
) -> None:
    params: dict[str, object] = {"vectors": vectors}
    if index_arn:
        params["indexArn"] = index_arn
    else:
        params["vectorBucketName"] = bucket
        params["indexName"] = index
    client.put_vectors(**params)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Embed rag_documents from the orchestrator DB and call s3vectors put_vectors."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(os.getenv("FLEET_DB_PATH", "services/orchestrator/data/fleet_health.db")),
        help="Path to fleet_health SQLite (same as FLEET_DB_PATH).",
    )
    parser.add_argument(
        "--bucket",
        default=os.getenv("FLEET_S3_VECTORS_BUCKET", ""),
        help="S3 vector bucket name (or rely on FLEET_S3_VECTORS_BUCKET).",
    )
    parser.add_argument(
        "--index",
        default=os.getenv("FLEET_S3_VECTORS_INDEX", ""),
        help="Vector index name (or rely on FLEET_S3_VECTORS_INDEX).",
    )
    parser.add_argument(
        "--index-arn",
        default=os.getenv("FLEET_S3_VECTORS_INDEX_ARN", ""),
        help="Vector index ARN (optional; overrides bucket+index when set).",
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=int(os.getenv("FLEET_S3_VECTORS_EMBEDDING_DIM", "384")),
        help="Must match the index dimension and the embedding provider output.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Vectors per put_vectors call (stay within account limits).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts only; do not call AWS.",
    )
    args = parser.parse_args()

    bucket = args.bucket.strip()
    index = args.index.strip()
    arn = args.index_arn.strip() or None
    if not arn and (not bucket or not index):
        print(
            "error: provide --bucket and --index, or --index-arn "
            "(or set FLEET_S3_VECTORS_* env vars).",
            file=sys.stderr,
        )
        return 2

    repo = FleetRepository(args.db_path.resolve())
    documents = repo.list_rag_documents()
    if not documents:
        print("No rag_documents in database; index runbooks first (index_documents.py).", file=sys.stderr)
        return 1

    embed = create_query_embedder(args.embedding_dim)
    batches: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    for doc in documents:
        _, row = embed_document_for_index(doc, embed)
        current.append(row)
        if len(current) >= args.batch_size:
            batches.append(current)
            current = []
    if current:
        batches.append(current)

    print(f"documents={len(documents)} batches={len(batches)} dim={args.embedding_dim}")
    if args.dry_run:
        return 0

    client = boto3.client("s3vectors")
    try:
        for batch in batches:
            _put_batch(
                client,
                bucket=bucket,
                index=index,
                index_arn=arn,
                vectors=batch,
            )
    except (BotoCoreError, ClientError) as exc:
        print(f"put_vectors failed: {exc}", file=sys.stderr)
        return 1

    print("put_vectors completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
