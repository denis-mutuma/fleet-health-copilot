import argparse
import json
from pathlib import Path

import httpx


def _request_json(*, operation: str, url: str, payload: dict[str, object]) -> httpx.Response:
    try:
        response = httpx.post(url, json=payload, timeout=10.0)
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"{operation} request to {url} timed out") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"{operation} request to {url} failed: {exc}") from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"{operation} request to {url} failed with HTTP {response.status_code}"
        ) from exc
    return response


def index_documents(documents_file: Path, base_url: str) -> None:
    url = f"{base_url.rstrip('/')}/v1/rag/documents"
    with documents_file.open("r", encoding="utf-8") as file:
        for line in file:
            payload = json.loads(line)
            _request_json(operation="index_documents", url=url, payload=payload)
            print(f"indexed {payload['document_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index runbooks/incidents into the orchestrator RAG endpoint."
    )
    parser.add_argument(
        "--documents-file",
        type=Path,
        default=Path("services/orchestrator/data/runbooks_detailed.jsonl")
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000"
    )
    args = parser.parse_args()

    index_documents(args.documents_file, args.base_url)


if __name__ == "__main__":
    main()
