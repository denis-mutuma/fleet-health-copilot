"""MCP-style tool adapter used by orchestrator chat orchestration.

This adapter provides a stable local tool contract with MCP-like names.
In the current phase, tools are served in-process against repository/retrieval
state. The interface is intentionally transport-agnostic for future remote MCP
server execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any


@dataclass
class MCPToolResult:
    tool_name: str
    params: dict[str, Any]
    output: dict[str, Any]
    latency_ms: float
    error: str | None = None


class MCPClientAdapter:
    def __init__(
        self,
        *,
        repository: Any,
        retrieval_backend: Any,
        logger: Any,
        tool_timeout_seconds: float = 8.0,
    ) -> None:
        self._repository = repository
        self._retrieval_backend = retrieval_backend
        self._logger = logger
        self._tool_timeout_seconds = tool_timeout_seconds

    def openai_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_operational_context",
                    "description": "Search runbooks and incident history for operational context.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_incidents",
                    "description": "List recent incidents.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_incident",
                    "description": "Read one incident by incident ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "incident_id": {"type": "string"},
                        },
                        "required": ["incident_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_incident",
                    "description": "Update incident status to open, acknowledged, or resolved.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "incident_id": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["open", "acknowledged", "resolved"],
                            },
                        },
                        "required": ["incident_id", "status"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_device_events",
                    "description": "List recent telemetry events for a device.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_id": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        },
                        "required": ["device_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "lookup_device_health",
                    "description": "Return nominal/anomalous health snapshot from latest event.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_id": {"type": "string"},
                        },
                        "required": ["device_id"],
                    },
                },
            },
        ]

    def call_tool(self, tool_name: str, params: dict[str, Any]) -> MCPToolResult:
        started_at = perf_counter()
        try:
            output = self._call_tool_impl(tool_name, params)
            latency_ms = (perf_counter() - started_at) * 1000
            return MCPToolResult(
                tool_name=tool_name,
                params=params,
                output=output,
                latency_ms=latency_ms,
                error=None,
            )
        except Exception as exc:
            latency_ms = (perf_counter() - started_at) * 1000
            self._logger.warning("MCP tool failed: %s (%s)", tool_name, exc)
            return MCPToolResult(
                tool_name=tool_name,
                params=params,
                output={},
                latency_ms=latency_ms,
                error=str(exc),
            )

    def _call_tool_impl(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "search_operational_context":
            query = str(params.get("query", "")).strip()
            if not query:
                raise ValueError("query is required")
            limit = int(params.get("limit", 5))
            hits = self._retrieval_backend.search(
                query=query,
                documents=self._repository.list_rag_documents(),
                limit=max(1, min(limit, 10)),
            )
            return {
                "query": query,
                "hits": [
                    {
                        "document_id": hit.document_id,
                        "source": hit.source,
                        "title": hit.title,
                        "score": hit.score,
                        "excerpt": hit.excerpt,
                    }
                    for hit in hits
                ],
            }

        if tool_name == "list_incidents":
            limit = int(params.get("limit", 10))
            incidents = self._repository.list_incidents()[: max(1, min(limit, 50))]
            return {
                "incidents": [incident.model_dump(mode="json") for incident in incidents],
            }

        if tool_name == "read_incident":
            incident_id = str(params.get("incident_id", "")).strip()
            if not incident_id:
                raise ValueError("incident_id is required")
            incident = self._repository.get_incident(incident_id)
            return {
                "incident": incident.model_dump(mode="json") if incident is not None else None,
            }

        if tool_name == "update_incident":
            incident_id = str(params.get("incident_id", "")).strip()
            status = str(params.get("status", "")).strip().lower()
            if not incident_id:
                raise ValueError("incident_id is required")
            if status not in {"open", "acknowledged", "resolved"}:
                raise ValueError("status must be one of open|acknowledged|resolved")
            incident = self._repository.update_incident_status(incident_id, status)
            return {
                "incident": incident.model_dump(mode="json") if incident is not None else None,
            }

        if tool_name == "query_device_events":
            device_id = str(params.get("device_id", "")).strip()
            limit = int(params.get("limit", 20))
            if not device_id:
                raise ValueError("device_id is required")
            events = [
                event.model_dump(mode="json")
                for event in self._repository.list_events()
                if event.device_id == device_id
            ][: max(1, min(limit, 50))]
            return {"device_id": device_id, "events": events}

        if tool_name == "lookup_device_health":
            device_id = str(params.get("device_id", "")).strip()
            if not device_id:
                raise ValueError("device_id is required")
            events = [
                event.model_dump(mode="json")
                for event in self._repository.list_events()
                if event.device_id == device_id
            ]
            latest = events[0] if events else None
            if latest is None:
                return {
                    "device_id": device_id,
                    "status": "unknown",
                    "latest_event": None,
                }
            is_anomalous = float(latest["value"]) > float(latest["threshold"])
            return {
                "device_id": device_id,
                "status": "anomalous" if is_anomalous else "nominal",
                "latest_event": latest,
            }

        raise ValueError(f"Unsupported tool: {tool_name}")
