import argparse
import json
from pathlib import Path

import httpx


def replay(events_file: Path, base_url: str) -> None:
    with events_file.open("r", encoding="utf-8") as file:
        for line in file:
            payload = json.loads(line)
            response = httpx.post(
                f"{base_url.rstrip('/')}/v1/events",
                json=payload,
                timeout=10.0
            )
            response.raise_for_status()
            print(f"ingested {payload['event_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay telemetry events into the orchestrator ingest endpoint."
    )
    parser.add_argument(
        "--events-file",
        type=Path,
        default=Path("services/orchestrator/data/sample_events.jsonl")
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000"
    )
    args = parser.parse_args()

    replay(args.events_file, args.base_url)


if __name__ == "__main__":
    main()
