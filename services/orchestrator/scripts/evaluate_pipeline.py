import argparse
import json
from pathlib import Path

import httpx


def evaluate(events_file: Path, base_url: str) -> dict[str, float]:
    total = 0
    expected_anomalies = 0
    generated_incidents = 0

    with events_file.open("r", encoding="utf-8") as file:
        for line in file:
            event = json.loads(line)
            total += 1
            expected = event["value"] > event["threshold"]
            if expected:
                expected_anomalies += 1

            response = httpx.post(
                f"{base_url.rstrip('/')}/v1/orchestrate/event",
                json=event,
                timeout=10.0
            )
            if response.status_code == 200:
                generated_incidents += 1

    precision = generated_incidents / max(generated_incidents, 1)
    recall = generated_incidents / max(expected_anomalies, 1)
    return {
        "events_total": float(total),
        "expected_anomalies": float(expected_anomalies),
        "incidents_generated": float(generated_incidents),
        "precision_proxy": precision,
        "recall_proxy": recall
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate end-to-end anomaly to incident flow."
    )
    parser.add_argument(
        "--events-file",
        type=Path,
        default=Path("services/orchestrator/data/sample_events.jsonl")
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    metrics = evaluate(events_file=args.events_file, base_url=args.base_url)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
