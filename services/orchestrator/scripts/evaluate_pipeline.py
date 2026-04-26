import argparse
import json
from pathlib import Path
from time import perf_counter

import httpx


def _expected_runbook(event: dict[str, object]) -> str | None:
    tags = set(event.get("tags", []))
    metric = str(event.get("metric", ""))
    if "network" in tags or "latency" in tags or "comms" in tags or "network" in metric:
        return "rb_network_latency_v1"
    if "battery" in tags or "thermal" in tags or "battery" in metric:
        return "rb_battery_thermal_v2"
    if "motor" in tags or "current" in tags or "motor" in metric:
        return "rb_motor_current_v1"
    return None


def _runbook_action_grounding(incident: dict[str, object]) -> bool | None:
    """True if some recommended action cites a Follow <runbook_id> present in evidence.runbooks."""
    evidence = incident.get("evidence", {})
    if not isinstance(evidence, dict):
        return None
    runbooks = evidence.get("runbooks", [])
    if not isinstance(runbooks, list) or not runbooks:
        return None
    actions = incident.get("recommended_actions", [])
    if not isinstance(actions, list) or not actions:
        return False
    ids = {str(x) for x in runbooks}
    for action in actions:
        text = str(action)
        if not text.startswith("Follow "):
            continue
        rest = text[len("Follow "):].split(":", 1)[0].strip()
        if rest in ids:
            return True
    return False


def _retrieval_reciprocal_rank(evidence: dict[str, object], expected_id: str) -> float:
    runbooks = evidence.get("runbooks", [])
    if not isinstance(runbooks, list) or expected_id not in runbooks:
        return 0.0
    return 1.0 / float(runbooks.index(expected_id) + 1)


def evaluate(events_file: Path, base_url: str) -> dict[str, float]:
    total = 0
    expected_anomalies = 0
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0
    retrieval_expected = 0
    retrieval_hits = 0
    retrieval_reciprocal_rank_sum = 0.0
    verifier_passes = 0
    verifier_total = 0
    runbook_grounding_expected = 0
    runbook_grounding_ok = 0
    agent_successes = 0
    response_latency_ms_total = 0.0
    time_to_diagnosis_ms_total = 0.0

    with events_file.open("r", encoding="utf-8") as file:
        for line in file:
            event = json.loads(line)
            total += 1
            expected = event["value"] > event["threshold"]
            if expected:
                expected_anomalies += 1

            started_at = perf_counter()
            response = httpx.post(
                f"{base_url.rstrip('/')}/v1/orchestrate/event",
                json=event,
                timeout=10.0
            )
            response_latency_ms_total += (perf_counter() - started_at) * 1000
            generated_incident = response.status_code == 200

            if response.status_code not in {200, 400}:
                response.raise_for_status()

            incident: dict[str, object] = {}
            if generated_incident and hasattr(response, "json"):
                incident = response.json()
            expected_runbook = _expected_runbook(event)
            if expected and expected_runbook:
                retrieval_expected += 1
                evidence = incident.get("evidence", {})
                runbooks = evidence.get("runbooks", []) if isinstance(evidence, dict) else []
                if expected_runbook in runbooks:
                    retrieval_hits += 1
                if isinstance(evidence, dict):
                    retrieval_reciprocal_rank_sum += _retrieval_reciprocal_rank(
                        evidence, expected_runbook
                    )

            verification = incident.get("verification", {})
            if isinstance(verification, dict) and verification.get("passed") is True:
                agent_successes += 1
            if generated_incident:
                verifier_total += 1
                if isinstance(verification, dict) and verification.get("passed") is True:
                    verifier_passes += 1
                grounded = _runbook_action_grounding(incident)
                if grounded is not None:
                    runbook_grounding_expected += 1
                    if grounded:
                        runbook_grounding_ok += 1
            time_to_diagnosis_ms_total += float(incident.get("latency_ms", 0.0))

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
    retrieval_hit_rate = retrieval_hits / retrieval_expected if retrieval_expected else 0.0
    retrieval_mean_reciprocal_rank = (
        retrieval_reciprocal_rank_sum / retrieval_expected if retrieval_expected else 0.0
    )
    verifier_pass_rate = verifier_passes / verifier_total if verifier_total else 0.0
    runbook_action_grounding_rate = (
        runbook_grounding_ok / runbook_grounding_expected if runbook_grounding_expected else 0.0
    )
    agent_task_success_rate = agent_successes / predicted_anomalies if predicted_anomalies else 0.0
    average_response_latency_ms = response_latency_ms_total / total if total else 0.0
    average_time_to_diagnosis_ms = (
        time_to_diagnosis_ms_total / predicted_anomalies if predicted_anomalies else 0.0
    )
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
        "accuracy": accuracy,
        "retrieval_expected": float(retrieval_expected),
        "retrieval_hits": float(retrieval_hits),
        "retrieval_hit_rate": retrieval_hit_rate,
        "retrieval_mean_reciprocal_rank": retrieval_mean_reciprocal_rank,
        "verifier_pass_rate": verifier_pass_rate,
        "runbook_action_grounding_rate": runbook_action_grounding_rate,
        "agent_task_success_rate": agent_task_success_rate,
        "average_response_latency_ms": average_response_latency_ms,
        "average_time_to_diagnosis_ms": average_time_to_diagnosis_ms
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
