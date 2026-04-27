from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from fleet_health_orchestrator.llm import (
    enrich_diagnosis_hypotheses,
    generate_action_plan,
    generate_diagnosis_hypotheses,
    refine_incident_summary,
)
from fleet_health_orchestrator.models import RetrievalHit, TelemetryEvent


class FakeOpenAIClient:
    def __init__(self, content: str) -> None:
        self._content = content
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **_: object) -> object:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._content)
                )
            ]
        )


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
    monkeypatch.setattr(
        "fleet_health_orchestrator.llm.OpenAI",
        lambda api_key: FakeOpenAIClient('["Evidence-aligned note from runbook context"]'),
    )

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


def test_generate_diagnosis_hypotheses_returns_json_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        "fleet_health_orchestrator.llm.OpenAI",
        lambda api_key: FakeOpenAIClient('["cooling degradation", "blocked airflow path"]'),
    )

    event = TelemetryEvent(
        event_id="e1",
        fleet_id="f",
        device_id="robot-01",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        metric="battery_temp_c",
        value=71.0,
        threshold=65.0,
        severity="high",
        tags=["battery", "thermal"],
    )
    hits = [
        RetrievalHit(
            document_id="rb_battery_thermal_v3",
            source="runbook",
            title="Battery thermal drift",
            score=1.0,
            excerpt="Inspect cooling ducts and reduce duty cycle.",
        )
    ]

    assert generate_diagnosis_hypotheses(event, hits) == [
        "cooling degradation",
        "blocked airflow path",
    ]


def test_generate_action_plan_returns_json_array(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        "fleet_health_orchestrator.llm.OpenAI",
        lambda api_key: FakeOpenAIClient(
            '["Follow rb_battery_thermal_v3: Reduce duty cycle and inspect cooling ducts."]'
        ),
    )

    event = TelemetryEvent(
        event_id="e1",
        fleet_id="f",
        device_id="robot-01",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        metric="battery_temp_c",
        value=71.0,
        threshold=65.0,
        severity="high",
        tags=["battery", "thermal"],
    )
    hits = [
        RetrievalHit(
            document_id="rb_battery_thermal_v3",
            source="runbook",
            title="Battery thermal drift",
            score=1.0,
            excerpt="Inspect cooling ducts and reduce duty cycle.",
        )
    ]

    assert generate_action_plan(event, hits) == [
        "Follow rb_battery_thermal_v3: Reduce duty cycle and inspect cooling ducts.",
    ]
