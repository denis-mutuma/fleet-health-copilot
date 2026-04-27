#!/usr/bin/env python3
"""Run a lightweight orchestration latency budget check against the ASGI app."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

from starlette.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]


class _TestClientShim:
    """Minimal surface used by ``evaluate(..., client=...)``."""

    def __init__(self, tc: TestClient) -> None:
        self._tc = tc

    def post(self, url: str, json: object | None = None):  # noqa: ANN201
        base = "http://testserver"
        path = url[len(base):] if url.startswith(base) else url
        if not path.startswith("/"):
            path = "/" + path
        return self._tc.post(path, json=json)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check average time-to-diagnosis latency against a fixed budget."
    )
    parser.add_argument(
        "--events-file",
        type=Path,
        default=REPO / "services/orchestrator/data/sample_events.jsonl"
    )
    parser.add_argument(
        "--runbooks-file",
        type=Path,
        default=REPO / "services/orchestrator/data/runbooks_detailed.jsonl"
    )
    parser.add_argument(
        "--budget-ms",
        type=float,
        default=float(os.getenv("ORCHESTRATOR_LATENCY_BUDGET_MS", "40"))
    )
    args = parser.parse_args()

    os.chdir(REPO)
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["FLEET_DB_PATH"] = db_path

    try:
        sys.path.insert(0, str(REPO / "services" / "orchestrator" / "src"))
        main_module = importlib.import_module("fleet_health_orchestrator.main")
        main_module = importlib.reload(main_module)

        sys.path.insert(0, str(REPO / "services" / "orchestrator" / "scripts"))
        evaluate_module = importlib.import_module("evaluate_pipeline")

        with TestClient(main_module.app) as tc:
            for line in args.runbooks_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                response = tc.post("/v1/rag/documents", json=json.loads(line))
                response.raise_for_status()

            metrics = evaluate_module.evaluate(
                events_file=args.events_file,
                base_url="http://testserver",
                client=_TestClientShim(tc)
            )

        avg_diag = float(metrics.get("average_time_to_diagnosis_ms", 0.0))
        avg_response = float(metrics.get("average_response_latency_ms", 0.0))
        result = {
            "budget_ms": args.budget_ms,
            "average_time_to_diagnosis_ms": avg_diag,
            "average_response_latency_ms": avg_response,
            "within_budget": avg_diag <= args.budget_ms,
            "events_total": metrics.get("events_total", 0.0),
            "incidents_generated": metrics.get("incidents_generated", 0.0)
        }
        print(json.dumps(result, indent=2))

        if avg_diag > args.budget_ms:
            print(
                f"Latency budget exceeded: {avg_diag:.2f}ms > {args.budget_ms:.2f}ms",
                file=sys.stderr
            )
            return 1
        return 0
    finally:
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
