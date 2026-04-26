from datetime import UTC, datetime

import pytest

from fleet_health_orchestrator.llm import enrich_diagnosis_hypotheses, refine_incident_summary
from fleet_health_orchestrator.models import RetrievalHit, TelemetryEvent


def test_enrich_diagnosis_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLEET_OPENAI_DIAGNOSIS_ENRICH", raising=False)
    event = TelemetryEvent(
        event_id="e1",
        fleet_id="f",
        device_id="d",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        metric="m",
        value=1.0,
        threshold=0.5,
        severity="low",
        tags=[]
    )
    hits = [
        RetrievalHit(
            document_id="rb_a",
            source="runbook",
            title="Example",
            score=1.0,
            excerpt="x"
        )
    ]
    assert enrich_diagnosis_hypotheses(event, hits, ["base"]) == []


def test_enrich_diagnosis_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEET_OPENAI_DIAGNOSIS_ENRICH", "true")
    monkeypatch.setenv("FLEET_OPENAI_API_KEY", "sk-test")

    payload = {
        "choices": [
            {
                "message": {
                    "content": '["Evidence-aligned note from runbook context"]'
                }
            }
        ]
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    def fake_post(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("fleet_health_orchestrator.llm.httpx.post", fake_post)

    event = TelemetryEvent(
        event_id="e1",
        fleet_id="f",
        device_id="d",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        metric="m",
        value=1.0,
        threshold=0.5,
        severity="low",
        tags=[]
    )
    hits = [
        RetrievalHit(
            document_id="rb_a",
            source="runbook",
            title="Example runbook",
            score=1.0,
            excerpt="x"
        )
    ]
    extra = enrich_diagnosis_hypotheses(event, hits, ["base"])
    assert len(extra) == 1
    assert "Evidence-aligned" in extra[0]


def test_refine_incident_summary_respects_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLEET_OPENAI_REPORT_REFINE", raising=False)
    event = TelemetryEvent(
        event_id="e1",
        fleet_id="f",
        device_id="d",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        metric="m",
        value=1.0,
        threshold=0.5,
        severity="low",
        tags=[]
    )
    assert refine_incident_summary(event, "draft") is None
