import argparse
import json
from pathlib import Path

import httpx


def index_documents(documents_file: Path, base_url: str) -> None:
    with documents_file.open("r", encoding="utf-8") as file:
        for line in file:
            payload = json.loads(line)
            response = httpx.post(
                f"{base_url.rstrip('/')}/v1/rag/documents",
                json=payload,
                timeout=10.0
            )
            response.raise_for_status()
            print(f"indexed {payload['document_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index runbooks/incidents into the orchestrator RAG endpoint."
    )
    parser.add_argument(
        "--documents-file",
        type=Path,
        default=Path("services/orchestrator/data/runbooks.jsonl")
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000"
    )
    args = parser.parse_args()

    index_documents(args.documents_file, args.base_url)


if __name__ == "__main__":
    main()
