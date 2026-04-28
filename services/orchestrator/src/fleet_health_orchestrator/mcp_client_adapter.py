"""MCP-style tool adapter used by orchestrator chat orchestration.

This adapter provides a stable local tool contract with MCP-like names.
In the current phase, tools are served in-process against repository/retrieval
state. The interface is intentionally transport-agnostic for future remote MCP
server execution.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx


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
        transport: str = "local",
        retrieval_base_url: str = "http://127.0.0.1:8000",
        incidents_base_url: str = "http://127.0.0.1:8000",
        telemetry_base_url: str = "http://127.0.0.1:8000",
    ) -> None:
        self._repository = repository
        self._retrieval_backend = retrieval_backend
        self._logger = logger
        self._tool_timeout_seconds = tool_timeout_seconds
        self._transport = transport.strip().lower() or "local"
        self._retrieval_base_url = retrieval_base_url.rstrip("/")
        self._incidents_base_url = incidents_base_url.rstrip("/")
        self._telemetry_base_url = telemetry_base_url.rstrip("/")

        if self._transport not in {"local", "http_json"}:
            raise ValueError("CHAT_TOOL_TRANSPORT must be 'local' or 'http_json'")

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
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self._call_tool_impl, tool_name, params)
            output = future.result(timeout=self._tool_timeout_seconds)
            latency_ms = (perf_counter() - started_at) * 1000
            return MCPToolResult(
                tool_name=tool_name,
                params=params,
                output=output,
                latency_ms=latency_ms,
                error=None,
            )
        except FutureTimeoutError:
            latency_ms = (perf_counter() - started_at) * 1000
            error = f"Tool timed out after {self._tool_timeout_seconds:.1f}s"
            self._logger.warning("MCP tool timeout: %s", tool_name)
            return MCPToolResult(
                tool_name=tool_name,
                params=params,
                output={},
                latency_ms=latency_ms,
                error=error,
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
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _call_tool_impl(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._transport == "http_json":
            return self._call_tool_http_json(tool_name, params)

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

    def _call_tool_http_json(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        timeout = httpx.Timeout(self._tool_timeout_seconds)

        if tool_name == "search_operational_context":
            query = str(params.get("query", "")).strip()
            if not query:
                raise ValueError("query is required")
            limit = max(1, min(int(params.get("limit", 5)), 10))
            response = self._request_json(
                tool_name=tool_name,
                request_fn=httpx.get,
                url=f"{self._retrieval_base_url}/v1/rag/search",
                params={"query": query, "limit": limit},
                timeout=timeout,
            )
            return {"query": query, "hits": response.json()}

        if tool_name == "list_incidents":
            limit = max(1, min(int(params.get("limit", 10)), 50))
            response = self._request_json(
                tool_name=tool_name,
                request_fn=httpx.get,
                url=f"{self._incidents_base_url}/v1/incidents",
                timeout=timeout,
            )
            return {"incidents": response.json()[:limit]}

        if tool_name == "read_incident":
            incident_id = str(params.get("incident_id", "")).strip()
            if not incident_id:
                raise ValueError("incident_id is required")
            response = self._request_json(
                tool_name=tool_name,
                request_fn=httpx.get,
                url=f"{self._incidents_base_url}/v1/incidents/{incident_id}",
                timeout=timeout,
                allow_statuses={404},
            )
            if response.status_code == 404:
                return {"incident": None}
            return {"incident": response.json()}

        if tool_name == "update_incident":
            incident_id = str(params.get("incident_id", "")).strip()
            status = str(params.get("status", "")).strip().lower()
            if not incident_id:
                raise ValueError("incident_id is required")
            if status not in {"open", "acknowledged", "resolved"}:
                raise ValueError("status must be one of open|acknowledged|resolved")
            response = self._request_json(
                tool_name=tool_name,
                request_fn=httpx.patch,
                url=f"{self._incidents_base_url}/v1/incidents/{incident_id}",
                json={"status": status},
                timeout=timeout,
                allow_statuses={404},
            )
            if response.status_code == 404:
                return {"incident": None}
            return {"incident": response.json()}

        if tool_name == "query_device_events":
            device_id = str(params.get("device_id", "")).strip()
            if not device_id:
                raise ValueError("device_id is required")
            limit = max(1, min(int(params.get("limit", 20)), 50))
            response = self._request_json(
                tool_name=tool_name,
                request_fn=httpx.get,
                url=f"{self._telemetry_base_url}/v1/events",
                timeout=timeout,
            )
            events = [event for event in response.json() if event.get("device_id") == device_id][:limit]
            return {"device_id": device_id, "events": events}

        if tool_name == "lookup_device_health":
            device_id = str(params.get("device_id", "")).strip()
            if not device_id:
                raise ValueError("device_id is required")
            response = self._request_json(
                tool_name=tool_name,
                request_fn=httpx.get,
                url=f"{self._telemetry_base_url}/v1/events",
                timeout=timeout,
            )
            events = [event for event in response.json() if event.get("device_id") == device_id][:1]
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

    def _request_json(
        self,
        *,
        tool_name: str,
        request_fn: Any,
        url: str,
        allow_statuses: set[int] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = request_fn(url, **kwargs)
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"{tool_name} request to {url} timed out") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"{tool_name} request to {url} failed: {exc}") from exc

        allowed = allow_statuses or set()
        if response.status_code in allowed:
            return response

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = self._response_error_detail(response)
            message = f"{tool_name} request to {url} failed with HTTP {response.status_code}"
            if detail:
                message = f"{message}: {detail}"
            raise RuntimeError(message) from exc
        return response

    def _response_error_detail(self, response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except Exception:
            return None

        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
        return None
