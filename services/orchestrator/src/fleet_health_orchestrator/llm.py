"""Optional OpenAI-assisted copy refinement and diagnosis enrichment."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from fleet_health_orchestrator.models import RetrievalHit, TelemetryEvent


def refine_incident_summary(
    event: TelemetryEvent,
    base_summary: str,
    *,
    api_key: str | None = None,
    model: str | None = None
) -> str | None:
    """Return a one-line refined summary, or None to keep ``base_summary``."""
    if os.getenv("FLEET_OPENAI_REPORT_REFINE", "").strip().lower() not in ("1", "true", "yes"):
        return None

    key = (api_key if api_key is not None else os.getenv("FLEET_OPENAI_API_KEY", "")).strip()
    if not key:
        return None

    m = (model if model is not None else os.getenv("FLEET_OPENAI_REPORT_MODEL", "gpt-4o-mini")).strip()

    system = (
        "You rewrite fleet incident summaries in one concise sentence for operators. "
        "Stay factual; do not invent causes or actions."
    )
    user = (
        f"device={event.device_id} metric={event.metric} value={event.value} "
        f"threshold={event.threshold} severity={event.severity}\n"
        f"Draft: {base_summary}"
    )

    try:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            },
            json={
                "model": m,
                "temperature": 0.2,
                "max_tokens": 120,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ]
            },
            timeout=45.0
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
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
    if os.getenv("FLEET_OPENAI_DIAGNOSIS_ENRICH", "").strip().lower() not in ("1", "true", "yes"):
        return []

    key = (api_key if api_key is not None else os.getenv("FLEET_OPENAI_API_KEY", "")).strip()
    if not key or not hits:
        return []

    m = (model if model is not None else os.getenv("FLEET_OPENAI_DIAGNOSIS_MODEL", "gpt-4o-mini")).strip()

    evidence = [{"document_id": h.document_id, "title": h.title, "source": h.source} for h in hits[:6]]
    system = (
        "You assist fleet incident triage. Using ONLY the JSON evidence list, propose at most "
        "two additional short hypothesis phrases (each under 120 characters). "
        "Do not invent device-specific facts not supported by evidence titles. "
        "Respond with ONLY a JSON array of strings (e.g. [\"...\"]). Use [] if nothing is justified."
    )
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
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            },
            json={
                "model": m,
                "temperature": 0.1,
                "max_tokens": 200,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ]
            },
            timeout=45.0
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return []
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            return []
        return _parse_json_array_response(content)
    except Exception:
        return []
