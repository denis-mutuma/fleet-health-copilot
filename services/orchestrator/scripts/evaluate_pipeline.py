import argparse
import json
from pathlib import Path

import httpx


def evaluate(events_file: Path, base_url: str) -> dict[str, float]:
    total = 0
    expected_anomalies = 0
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0

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
            generated_incident = response.status_code == 200

            if response.status_code not in {200, 400}:
                response.raise_for_status()

            if expected and generated_incident:
                true_positives += 1
            elif expected and not generated_incident:
                false_negatives += 1
            elif not expected and generated_incident:
                false_positives += 1
            else:
                true_negatives += 1

    predicted_anomalies = true_positives + false_positives
    precision = true_positives / predicted_anomalies if predicted_anomalies else 0.0
    recall = true_positives / expected_anomalies if expected_anomalies else 0.0
    accuracy = (true_positives + true_negatives) / total if total else 0.0
    return {
        "events_total": float(total),
        "expected_anomalies": float(expected_anomalies),
        "incidents_generated": float(predicted_anomalies),
        "true_positives": float(true_positives),
        "false_positives": float(false_positives),
        "false_negatives": float(false_negatives),
        "true_negatives": float(true_negatives),
        "precision": precision,
        "recall": recall,
        "accuracy": accuracy
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
