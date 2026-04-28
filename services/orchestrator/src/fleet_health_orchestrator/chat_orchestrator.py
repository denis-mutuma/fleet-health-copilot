"""OpenAI-driven chat orchestration with MCP-style tool execution and traces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from openai import OpenAI

from fleet_health_orchestrator.llm import openai_trace
from fleet_health_orchestrator.mcp_client_adapter import MCPClientAdapter, MCPToolResult


@dataclass
class ChatTurnResult:
    content: str
    citations: list[dict[str, Any]]
    action: str | None
    action_status: str | None
    action_payload: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    trace_spans: list[dict[str, Any]]
    llm_cost_usd: float | None


@dataclass
class ParsedToolCall:
    params: dict[str, Any]
    error: str | None = None


class ChatToolOrchestrator:
    def __init__(
        self,
        *,
        logger: Any,
        settings: Any,
        mcp_adapter: MCPClientAdapter,
    ) -> None:
        self._logger = logger
        self._settings = settings
        self._mcp_adapter = mcp_adapter

    def can_use_llm(self) -> bool:
        chat_enabled = bool(
            getattr(
                self._settings,
                "effective_llm_chat_enabled",
                getattr(self._settings, "llm_chat_enabled", False),
            )
        )
        return bool(chat_enabled and self._settings.openai_api_key.strip())

    def run_turn(
        self,
        *,
        user_content: str,
        session: Any,
        chat_history: list[dict[str, Any]],
    ) -> ChatTurnResult | None:
        if not self.can_use_llm():
            return None

        client = OpenAI(api_key=self._settings.openai_api_key)
        trace_spans: list[dict[str, Any]] = []
        executed_tools: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []

        history_messages = self._history_for_model(chat_history)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            *history_messages,
            {
                "role": "user",
                "content": user_content,
            },
        ]

        action = "rag_answer"
        action_status = "success"
        action_payload: dict[str, Any] = {}
        llm_cost_usd: float | None = None
        accumulated_cost_usd = 0.0

        with openai_trace(
            "fleet-health.chat.session",
            metadata={
                "session_id": session.session_id,
                "incident_id": session.incident_id,
            },
        ):
            final_content = ""
            max_tool_calls = int(self._settings.chat_tool_max_calls_per_turn)
            tool_call_count = 0

            while True:
                started = perf_counter()
                response = client.chat.completions.create(
                    model=self._settings.llm_chat_model,
                    temperature=self._settings.llm_chat_temperature,
                    max_tokens=self._settings.llm_chat_max_output_tokens,
                    messages=messages,
                    tools=self._mcp_adapter.openai_tool_definitions(),
                    tool_choice="auto",
                )
                latency_ms = (perf_counter() - started) * 1000

                usage = getattr(response, "usage", None)
                response_cost_usd = self._estimate_response_cost_usd(usage)
                if response_cost_usd is not None:
                    accumulated_cost_usd += response_cost_usd
                    llm_cost_usd = round(accumulated_cost_usd, 8)
                max_turn_cost_usd = float(getattr(self._settings, "llm_chat_max_turn_cost_usd", 0.0) or 0.0)
                if max_turn_cost_usd > 0 and accumulated_cost_usd > max_turn_cost_usd:
                    final_content = (
                        "I stopped this turn because the configured model cost budget was exceeded. "
                        "Please narrow your request and try again."
                    )
                    action_status = "error"
                    action = "cost_limit"
                    action_payload = {
                        "max_turn_cost_usd": round(max_turn_cost_usd, 8),
                        "estimated_turn_cost_usd": round(accumulated_cost_usd, 8),
                    }
                    trace_spans.append(
                        {
                            "span_name": "chat.cost_guardrail",
                            "status": "error",
                            "latency_ms": 0.0,
                            "metadata": action_payload,
                            "error": "turn_cost_exceeded",
                        }
                    )
                    break
                trace_spans.append(
                    {
                        "span_name": "openai.chat.completion",
                        "status": "success",
                        "latency_ms": latency_ms,
                        "metadata": {
                            "model": self._settings.llm_chat_model,
                            "prompt_tokens": getattr(usage, "prompt_tokens", None),
                            "completion_tokens": getattr(usage, "completion_tokens", None),
                            "total_tokens": getattr(usage, "total_tokens", None),
                            "estimated_cost_usd": response_cost_usd,
                        },
                    }
                )

                message = response.choices[0].message
                if message.tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": message.content or "",
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": call.type,
                                    "function": {
                                        "name": call.function.name,
                                        "arguments": call.function.arguments,
                                    },
                                }
                                for call in message.tool_calls
                            ],
                        }
                    )

                    for call in message.tool_calls:
                        if tool_call_count >= max_tool_calls:
                            final_content = (
                                "I hit the tool-execution safety limit for this turn. "
                                "Please narrow your request and try again."
                            )
                            action_status = "error"
                            action = "tool_limit"
                            action_payload = {
                                "max_tool_calls": max_tool_calls,
                                "executed_tool_calls": tool_call_count,
                            }
                            break

                        tool_call_count += 1
                        parsed_call = self._safe_load_json(call.function.arguments)
                        if parsed_call.error is not None:
                            tool_result = MCPToolResult(
                                tool_name=call.function.name,
                                params={},
                                output={},
                                latency_ms=0.0,
                                error=parsed_call.error,
                            )
                        else:
                            tool_result = self._mcp_adapter.call_tool(call.function.name, parsed_call.params)
                        executed_tools.append(self._serialize_tool_result(tool_result))
                        trace_spans.append(self._tool_span(tool_result))

                        if call.function.name == "search_operational_context" and not tool_result.error:
                            for hit in tool_result.output.get("hits", []):
                                if isinstance(hit, dict):
                                    citations.append(
                                        {
                                            "document_id": hit.get("document_id", ""),
                                            "source": hit.get("source", "manual"),
                                            "title": hit.get("title", "Untitled"),
                                            "score": float(hit.get("score", 0.0) or 0.0),
                                            "excerpt": hit.get("excerpt", ""),
                                        }
                                    )

                        tool_output_payload = {
                            "ok": tool_result.error is None,
                            "result": tool_result.output,
                            "error": tool_result.error,
                        }
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": json.dumps(tool_output_payload),
                            }
                        )

                    if action == "tool_limit":
                        break

                    continue

                final_content = (message.content or "").strip()
                break

            if not final_content:
                final_content = "I could not generate a complete response for that request."
                action_status = "error"
                action = "rag_answer"

            if citations:
                top_docs = [c["document_id"] for c in citations[:3] if c.get("document_id")]
                citation_payload = {
                    "hit_count": len(citations),
                    "top_documents": top_docs,
                    "tool_calls": len(executed_tools),
                }
                action_payload = {**citation_payload, **action_payload}

            return ChatTurnResult(
                content=final_content,
                citations=citations,
                action=action,
                action_status=action_status,
                action_payload=action_payload,
                tool_calls=executed_tools,
                trace_spans=trace_spans,
                llm_cost_usd=llm_cost_usd,
            )

    def _history_for_model(self, chat_history: list[dict[str, Any]]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        # Keep context window predictable and avoid replaying tool metadata.
        for item in chat_history[-12:]:
            role = item.get("role")
            content = str(item.get("content", "")).strip()
            if role not in ("user", "assistant") or not content:
                continue
            out.append({"role": role, "content": content})
        return out

    def _system_prompt(self) -> str:
        return (
            "You are Fleet Health Copilot, an operations assistant for robotics and IoT fleets. "
            "Use tools for grounded answers when data is needed. "
            "Prefer concise, actionable responses. "
            "If evidence is unavailable, explicitly say so and ask for a narrower query. "
            "Respect slash commands when users type them, but still use tools as needed."
        )

    def _safe_load_json(self, raw: str) -> ParsedToolCall:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return ParsedToolCall(params=parsed)
            return ParsedToolCall(params={}, error="Tool arguments must decode to a JSON object.")
        except json.JSONDecodeError as exc:
            return ParsedToolCall(params={}, error=f"Tool arguments are not valid JSON: {exc.msg}.")

    def _serialize_tool_result(self, tool_result: MCPToolResult) -> dict[str, Any]:
        return {
            "tool_name": tool_result.tool_name,
            "input": tool_result.params,
            "output": tool_result.output,
            "latency_ms": tool_result.latency_ms,
            "error": tool_result.error,
        }

    def _tool_span(self, tool_result: MCPToolResult) -> dict[str, Any]:
        return {
            "span_name": f"mcp.tool.{tool_result.tool_name}",
            "status": "error" if tool_result.error else "success",
            "latency_ms": tool_result.latency_ms,
            "metadata": {
                "params": tool_result.params,
            },
            "error": tool_result.error,
        }

    def _estimate_response_cost_usd(self, usage: Any) -> float | None:
        if usage is None:
            return None

        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        if prompt_tokens is None and completion_tokens is None:
            return None

        input_rate = float(getattr(self._settings, "llm_chat_input_cost_per_1k_tokens_usd", 0.0) or 0.0)
        output_rate = float(getattr(self._settings, "llm_chat_output_cost_per_1k_tokens_usd", 0.0) or 0.0)
        prompt_count = float(prompt_tokens or 0)
        completion_count = float(completion_tokens or 0)
        estimated_cost = (prompt_count / 1000.0 * input_rate) + (completion_count / 1000.0 * output_rate)
        return round(estimated_cost, 8)
