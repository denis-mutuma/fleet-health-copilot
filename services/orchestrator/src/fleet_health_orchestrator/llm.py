"""Optional OpenAI-assisted copy refinement for incident summaries."""

from __future__ import annotations

import os
from typing import Any

import httpx

from fleet_health_orchestrator.models import TelemetryEvent


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
