"""RAG document ingestion helpers for parsing, chunking, and vector indexing."""

from __future__ import annotations

import hashlib
import json
import time
from io import BytesIO
from html.parser import HTMLParser
from collections.abc import Callable
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from fleet_health_orchestrator.embeddings import create_query_embedder, embed_document_for_index

_ALLOWED_UPLOAD_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".jsonl",
    ".csv",
    ".log",
    ".html",
    ".htm",
    ".pdf",
    ".docx",
}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self._chunks.append(cleaned)

    def text(self) -> str:
        return "\n".join(self._chunks)


def is_supported_upload(filename: str) -> bool:
    lower = filename.strip().lower()
    return any(lower.endswith(ext) for ext in _ALLOWED_UPLOAD_SUFFIXES)


def extract_text_from_bytes(filename: str, raw_bytes: bytes) -> str:
    """Decode uploaded file bytes to plain text.

    This supports text-centric formats used for operational runbooks and notes.
    """
    if not raw_bytes:
        return ""

    lower = filename.strip().lower()
    if lower.endswith(".html") or lower.endswith(".htm"):
        decoded = raw_bytes.decode("utf-8", errors="replace")
        parser = _HTMLTextExtractor()
        parser.feed(decoded)
        return parser.text()

    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except Exception as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError("PDF ingestion requires the pypdf package.") from exc
        reader = PdfReader(BytesIO(raw_bytes))
        return "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()

    if lower.endswith(".docx"):
        try:
            from docx import Document
        except Exception as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError("DOCX ingestion requires the python-docx package.") from exc
        doc = Document(BytesIO(raw_bytes))
        return "\n".join(paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip())

    if lower.endswith(".json") or lower.endswith(".jsonl"):
        decoded = raw_bytes.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(decoded)
            return json.dumps(parsed, indent=2, ensure_ascii=True)
        except json.JSONDecodeError:
            return decoded

    return raw_bytes.decode("utf-8", errors="replace")


def generate_document_id(*, filename: str, title: str, content: str) -> str:
    seed = f"{filename}\n{title}\n{content[:4000]}".encode("utf-8", errors="ignore")
    digest = hashlib.sha256(seed).hexdigest()[:16]
    safe_name = _safe_slug(title or filename)
    return f"doc_{safe_name}_{digest}"


def chunk_text(text: str, *, chunk_size_chars: int, chunk_overlap_chars: int) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []

    if chunk_overlap_chars >= chunk_size_chars:
        raise ValueError("chunk_overlap_chars must be less than chunk_size_chars")

    chunks: list[str] = []
    start = 0
    text_len = len(stripped)
    step = chunk_size_chars - chunk_overlap_chars

    while start < text_len:
        end = min(start + chunk_size_chars, text_len)
        if end < text_len:
            # Favor a nearby whitespace boundary to keep chunks readable and searchable.
            split_at = stripped.rfind(" ", start, end)
            if split_at > start + int(chunk_size_chars * 0.6):
                end = split_at
        chunk = stripped[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = max(start + step, end - chunk_overlap_chars)

    return chunks


def build_chunk_documents(
    *,
    document_id: str,
    source: str,
    title: str,
    tags: list[str],
    chunks: list[str],
) -> list[dict[str, object]]:
    docs: list[dict[str, object]] = []
    for idx, chunk in enumerate(chunks, start=1):
        chunk_id = f"{document_id}#chunk-{idx:04d}"
        chunk_title = f"{title} (chunk {idx}/{len(chunks)})"
        docs.append(
            {
                "document_id": chunk_id,
                "source": source,
                "title": chunk_title,
                "content": chunk,
                "tags": tags,
            }
        )
    return docs


def index_documents_to_s3_vectors(
    *,
    documents: list[dict[str, object]],
    bucket: str,
    index: str,
    index_arn: str,
    embedding_dimension: int,
    embedding_provider: str,
    embedding_model: str,
    openai_api_key: str,
    batch_size: int,
) -> int:
    if not documents:
        return 0

    embed = create_query_embedder(
        embedding_dimension,
        provider=embedding_provider,
        openai_api_key=openai_api_key,
        openai_model=embedding_model,
    )
    client = boto3.client("s3vectors")

    indexed = 0
    batch: list[dict[str, Any]] = []

    for doc in documents:
        _, row = embed_document_for_index(doc, embed)
        batch.append(row)
        # Keep request payloads bounded for S3 Vectors API stability.
        if len(batch) >= batch_size:
            _put_vectors(
                client=client,
                bucket=bucket,
                index=index,
                index_arn=index_arn,
                vectors=batch,
            )
            indexed += len(batch)
            batch = []

    if batch:
        _put_vectors(
            client=client,
            bucket=bucket,
            index=index,
            index_arn=index_arn,
            vectors=batch,
        )
        indexed += len(batch)

    return indexed


def delete_documents_from_s3_vectors(
    *,
    document_keys: list[str],
    bucket: str,
    index: str,
    index_arn: str,
    batch_size: int,
) -> int:
    keys = [key.strip() for key in document_keys if key and key.strip()]
    if not keys:
        return 0

    client = boto3.client("s3vectors")
    deleted = 0

    for start in range(0, len(keys), max(1, batch_size)):
        batch = keys[start : start + max(1, batch_size)]
        _delete_vectors(
            client=client,
            bucket=bucket,
            index=index,
            index_arn=index_arn,
            keys=batch,
        )
        deleted += len(batch)

    return deleted


def _put_vectors(
    *,
    client: Any,
    bucket: str,
    index: str,
    index_arn: str,
    vectors: list[dict[str, object]],
) -> None:
    params: dict[str, object] = {"vectors": vectors}
    if index_arn.strip():
        params["indexArn"] = index_arn.strip()
    else:
        params["vectorBucketName"] = bucket
        params["indexName"] = index

    def _op() -> None:
        client.put_vectors(**params)

    _with_retries(
        operation=_op,
        error_message="Failed to index chunks in S3 Vectors. Validate IAM, index configuration, and embedding dimensions.",
    )


def _delete_vectors(
    *,
    client: Any,
    bucket: str,
    index: str,
    index_arn: str,
    keys: list[str],
) -> None:
    params: dict[str, object] = {"keys": keys}
    if index_arn.strip():
        params["indexArn"] = index_arn.strip()
    else:
        params["vectorBucketName"] = bucket
        params["indexName"] = index

    delete_method = getattr(client, "delete_vectors", None)
    if delete_method is None:
        raise RuntimeError("S3 Vectors client does not expose delete_vectors.")

    def _op() -> None:
        delete_method(**params)

    _with_retries(
        operation=_op,
        error_message="Failed to delete vectors in S3 Vectors. Validate IAM and index configuration.",
    )


def _safe_slug(value: str) -> str:
    out = []
    for ch in value.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_", "."):
            out.append("-")
    collapsed = "".join(out).strip("-")
    if not collapsed:
        return "document"
    while "--" in collapsed:
        collapsed = collapsed.replace("--", "-")
    return collapsed[:48]


def _with_retries(
    *,
    operation: Callable[[], None],
    error_message: str,
    attempts: int = 3,
    base_delay_seconds: float = 0.2,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            operation()
            return
        except (BotoCoreError, ClientError) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            # Simple exponential backoff for transient S3 Vectors errors.
            time.sleep(base_delay_seconds * (2 ** (attempt - 1)))

    raise RuntimeError(error_message) from last_error
