"""OpenAI-assisted hypothesis, planning, and copy refinement helpers."""

from __future__ import annotations

import json
import os
import re
from contextlib import nullcontext
from typing import Any

from openai import OpenAI

from fleet_health_orchestrator.models import RetrievalHit, TelemetryEvent

try:
    from openai import trace as openai_trace
except ImportError:  # pragma: no cover - older SDK fallback
    def openai_trace(*_args: object, **_kwargs: object):
        return nullcontext()


SUMMARY_SYSTEM_PROMPT = (
    "You rewrite fleet incident summaries for on-call operators. "
    "Output exactly one sentence under 160 characters. "
    "Keep it factual, include the metric and affected device, and avoid speculation."
)

ENRICH_DIAGNOSIS_SYSTEM_PROMPT = (
    "You assist fleet incident triage. Using ONLY the provided evidence list, "
    "propose up to two additional root-cause hypotheses. "
    "Each item must be short, concrete, and under 120 characters. "
    "Return ONLY a JSON array of strings; use [] when evidence is insufficient."
)

GENERATE_DIAGNOSIS_SYSTEM_PROMPT = (
    "You are a fleet operations analyst. Based only on the telemetry event and retrieval evidence, "
    "return a JSON array with up to 4 short root-cause hypotheses. "
    "No markdown, no explanation, no fabricated facts. Return [] when evidence is weak."
)

ACTION_PLAN_SYSTEM_PROMPT = (
    "You write safe operator actions for industrial fleet incidents. "
    "Return ONLY a JSON array with 1 to 4 action strings. "
    "Each action must be conservative and directly executable by an operator. "
    "For runbook-grounded actions, start with 'Follow <runbook_id>:'. "
    "Do not output any item that cannot be grounded in the provided runbooks."
)


def _llm_enabled(flag_name: str) -> bool:
    flag_value = os.getenv(flag_name, "").strip().lower()
    if flag_value:
        return flag_value in ("1", "true", "yes")
    return bool(_resolve_api_key())


def _resolve_api_key(api_key: str | None = None) -> str:
    return (
        api_key
        if api_key is not None
        else os.getenv("OPENAI_API_KEY") or os.getenv("FLEET_OPENAI_API_KEY", "")
    ).strip()


def _client(api_key: str | None = None) -> OpenAI | None:
    key = _resolve_api_key(api_key)
    if not key:
        return None
    return OpenAI(api_key=key)


def _extract_message_content(response: Any) -> str | None:
    choices = getattr(response, "choices", None)
    if not choices:
        return None
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n".join(parts) if parts else None
    return None


def _extract_response_text(response: Any) -> str | None:
    # Prefer top-level output_text from the Responses API when present.
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return None

    parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for block in content:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())

    return "\n".join(parts) if parts else None


def _resolve_model(
    *,
    explicit: str | None,
    primary_env: str,
    legacy_env: str,
    default: str,
) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()
    return (
        os.getenv(primary_env, "").strip()
        or os.getenv(legacy_env, "").strip()
        or default
    )


def _chat_completion(
    *,
    trace_name: str,
    system: str,
    user: str,
    model: str,
    temperature: float,
    max_tokens: int,
    api_key: str | None = None
) -> str | None:
    client = _client(api_key)
    if client is None:
        return None

    with openai_trace(trace_name):
        # Use Responses API first for tracing and forward-compatible OpenAI behavior.
        if hasattr(client, "responses"):
            response = client.responses.create(
                model=model,
                temperature=temperature,
                max_output_tokens=max_tokens,
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": system}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user}]},
                ],
            )
            text = _extract_response_text(response)
            if text is not None:
                return text

        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return _extract_message_content(response)


def refine_incident_summary(
    event: TelemetryEvent,
    base_summary: str,
    *,
    api_key: str | None = None,
    model: str | None = None
) -> str | None:
    """Return a one-line refined summary, or None to keep ``base_summary``."""
    if not _llm_enabled("FLEET_OPENAI_REPORT_REFINE"):
        return None

    key = _resolve_api_key(api_key)
    if not key:
        return None

    m = _resolve_model(
        explicit=model,
        primary_env="LLM_REPORT_MODEL",
        legacy_env="FLEET_OPENAI_REPORT_MODEL",
        default="gpt-5.4-mini",
    )

    system = SUMMARY_SYSTEM_PROMPT
    user = (
        f"device={event.device_id} metric={event.metric} value={event.value} "
        f"threshold={event.threshold} severity={event.severity}\n"
        f"Draft: {base_summary}"
    )

    try:
        content = _chat_completion(
            trace_name="fleet-health.refine-incident-summary",
            system=system,
            user=user,
            model=m,
            temperature=0.2,
            max_tokens=120,
            api_key=key,
        )
        if not isinstance(content, str):
            return None
        line = content.strip().split("\n")[0].strip()
        return line if line else None
    except Exception:
        return None


def _parse_json_array_response(content: str) -> list[str]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        if "```" in text:
            text = text.split("```", 1)[0].strip()
    payload = json.loads(text)
    if not isinstance(payload, list):
        return []
    out: list[str] = []
    for item in payload[:2]:
        if isinstance(item, str) and item.strip():
            line = item.strip()[:200]
            if line not in out:
                out.append(line)
    return out


def enrich_diagnosis_hypotheses(
    event: TelemetryEvent,
    hits: list[RetrievalHit],
    base_hypotheses: list[str],
    *,
    api_key: str | None = None,
    model: str | None = None
) -> list[str]:
    """Return up to two extra hypotheses grounded in retrieval titles, or []."""
    if not _llm_enabled("FLEET_OPENAI_DIAGNOSIS_ENRICH"):
        return []

    key = _resolve_api_key(api_key)
    if not key or not hits:
        return []

    m = _resolve_model(
        explicit=model,
        primary_env="LLM_DIAGNOSIS_MODEL",
        legacy_env="FLEET_OPENAI_DIAGNOSIS_MODEL",
        default="gpt-5.4-mini",
    )

    evidence = [{"document_id": h.document_id, "title": h.title, "source": h.source} for h in hits[:6]]
    system = ENRICH_DIAGNOSIS_SYSTEM_PROMPT
    user = json.dumps(
        {
            "device_id": event.device_id,
            "metric": event.metric,
            "severity": event.severity,
            "existing_hypotheses": base_hypotheses[:8],
            "retrieval_evidence": evidence
        },
        ensure_ascii=False
    )

    try:
        content = _chat_completion(
            trace_name="fleet-health.enrich-diagnosis-hypotheses",
            system=system,
            user=user,
            model=m,
            temperature=0.1,
            max_tokens=200,
            api_key=key,
        )
        if not isinstance(content, str):
            return []
        return _parse_json_array_response(content)
    except Exception:
        return []


def generate_diagnosis_hypotheses(
    event: TelemetryEvent,
    hits: list[RetrievalHit],
    *,
    api_key: str | None = None,
    model: str | None = None
) -> list[str]:
    """Return grounded diagnosis hypotheses from OpenAI, or [] when unavailable."""
    key = _resolve_api_key(api_key)
    if not key or not hits:
        return []

    m = _resolve_model(
        explicit=model,
        primary_env="LLM_DIAGNOSIS_MODEL",
        legacy_env="FLEET_OPENAI_DIAGNOSIS_MODEL",
        default="gpt-5.4-mini",
    )
    evidence = [
        {
            "document_id": hit.document_id,
            "source": hit.source,
            "title": hit.title,
            "excerpt": hit.excerpt,
        }
        for hit in hits[:6]
    ]
    system = GENERATE_DIAGNOSIS_SYSTEM_PROMPT
    user = json.dumps(
        {
            "event": {
                "device_id": event.device_id,
                "fleet_id": event.fleet_id,
                "metric": event.metric,
                "value": event.value,
                "threshold": event.threshold,
                "severity": event.severity,
                "tags": event.tags,
            },
            "retrieval_evidence": evidence,
        },
        ensure_ascii=False,
    )

    try:
        content = _chat_completion(
            trace_name="fleet-health.generate-diagnosis-hypotheses",
            system=system,
            user=user,
            model=m,
            temperature=0.1,
            max_tokens=220,
            api_key=key,
        )
        if not isinstance(content, str):
            return []
        return _parse_json_array_response(content)
    except Exception:
        return []


def generate_action_plan(
    event: TelemetryEvent,
    runbook_hits: list[RetrievalHit],
    *,
    api_key: str | None = None,
    model: str | None = None
) -> list[str]:
    """Return grounded operator actions from OpenAI, or [] when unavailable."""
    key = _resolve_api_key(api_key)
    if not key or not runbook_hits:
        return []

    m = _resolve_model(
        explicit=model,
        primary_env="LLM_REPORT_MODEL",
        legacy_env="FLEET_OPENAI_REPORT_MODEL",
        default="gpt-5.4-mini",
    )
    runbooks = [
        {
            "document_id": hit.document_id,
            "title": hit.title,
            "excerpt": hit.excerpt,
        }
        for hit in runbook_hits[:4]
    ]
    system = ACTION_PLAN_SYSTEM_PROMPT
    user = json.dumps(
        {
            "event": {
                "device_id": event.device_id,
                "metric": event.metric,
                "severity": event.severity,
                "tags": event.tags,
            },
            "runbooks": runbooks,
        },
        ensure_ascii=False,
    )

    try:
        content = _chat_completion(
            trace_name="fleet-health.generate-action-plan",
            system=system,
            user=user,
            model=m,
            temperature=0.1,
            max_tokens=260,
            api_key=key,
        )
        if not isinstance(content, str):
            return []
        return _parse_json_array_response(content)
    except Exception:
        return []
