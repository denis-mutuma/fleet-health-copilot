"""In-process metrics collector with Prometheus text rendering.

The orchestrator already tracks a small set of runtime counters and gauges.
This module keeps that flat-dict compatibility while also supporting
histogram-style observations and Prometheus exposition text.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _sanitize_metric_name(name: str) -> str:
    return name.replace(".", "_").replace("-", "_")


@dataclass
class HistogramMetric:
    name: str
    buckets: tuple[float, ...]
    help_text: str
    counts: list[int] = field(init=False)
    total_count: int = 0
    total_sum: float = 0.0

    def __post_init__(self) -> None:
        self.counts = [0 for _ in self.buckets]

    def observe(self, value: float) -> None:
        observed = float(value)
        self.total_count += 1
        self.total_sum += observed
        for idx, upper_bound in enumerate(self.buckets):
            if observed <= upper_bound:
                self.counts[idx] += 1

    def render(self) -> list[str]:
        metric_name = _sanitize_metric_name(self.name)
        lines = [
            f"# HELP {metric_name} {self.help_text}",
            f"# TYPE {metric_name} histogram",
        ]
        cumulative = 0
        for upper_bound, bucket_count in zip(self.buckets, self.counts, strict=False):
            cumulative += bucket_count
            bound = "+Inf" if upper_bound == float("inf") else _format_number(upper_bound)
            lines.append(f'{metric_name}_bucket{{le="{bound}"}} {cumulative}')
        lines.append(f"{metric_name}_count {self.total_count}")
        lines.append(f"{metric_name}_sum {_format_number(self.total_sum)}")
        return lines


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.8f}".rstrip("0").rstrip(".")


class RuntimeMetrics:
    """Collector that preserves dict-like access for legacy call sites."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {
            "events_ingested_total": 0.0,
            "incidents_generated_total": 0.0,
            "rag_queries_total": 0.0,
            "requests_total": 0.0,
            "llm_chat_turns_total": 0.0,
        }
        self._gauges: dict[str, float] = {
            "rag_query_latency_ms_last": 0.0,
            "orchestration_latency_ms_last": 0.0,
            "request_latency_ms_last": 0.0,
            "llm_chat_turn_cost_usd_last": 0.0,
            "llm_chat_turn_latency_ms_last": 0.0,
        }
        self._histograms: dict[str, HistogramMetric] = {
            "request_latency_ms": HistogramMetric(
                name="request_latency_ms",
                help_text="HTTP request latency in milliseconds.",
                buckets=(10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, float("inf")),
            ),
            "orchestration_latency_ms": HistogramMetric(
                name="orchestration_latency_ms",
                help_text="Incident orchestration latency in milliseconds.",
                buckets=(50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, float("inf")),
            ),
            "rag_query_latency_ms": HistogramMetric(
                name="rag_query_latency_ms",
                help_text="RAG query latency in milliseconds.",
                buckets=(10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, float("inf")),
            ),
            "llm_chat_turn_cost_usd": HistogramMetric(
                name="llm_chat_turn_cost_usd",
                help_text="Estimated LLM chat turn cost in USD.",
                buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, float("inf")),
            ),
            "llm_chat_turn_latency_ms": HistogramMetric(
                name="llm_chat_turn_latency_ms",
                help_text="LLM chat turn latency in milliseconds.",
                buckets=(50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, float("inf")),
            ),
        }

    def __getitem__(self, key: str) -> float:
        if key in self._counters:
            return self._counters[key]
        if key in self._gauges:
            return self._gauges[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: float) -> None:
        if key in self._counters:
            self._counters[key] = float(value)
            return
        if key in self._gauges:
            self._gauges[key] = float(value)
            return
        self._gauges[key] = float(value)

    def copy(self) -> dict[str, float]:
        return {**self._counters, **self._gauges}

    def increment(self, name: str, amount: float = 1.0) -> None:
        self._counters[name] = self._counters.get(name, 0.0) + float(amount)

    def set_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = float(value)

    def observe(self, name: str, value: float) -> None:
        histogram = self._histograms.get(name)
        if histogram is None:
            raise KeyError(name)
        histogram.observe(float(value))

    def observe_request(self, latency_ms: float) -> None:
        self.increment("requests_total")
        self.set_gauge("request_latency_ms_last", latency_ms)
        self.observe("request_latency_ms", latency_ms)

    def observe_orchestration(self, latency_ms: float) -> None:
        self.set_gauge("orchestration_latency_ms_last", latency_ms)
        self.observe("orchestration_latency_ms", latency_ms)

    def observe_rag_query(self, latency_ms: float) -> None:
        self.increment("rag_queries_total")
        self.set_gauge("rag_query_latency_ms_last", latency_ms)
        self.observe("rag_query_latency_ms", latency_ms)

    def observe_llm_chat_turn(self, *, latency_ms: float | None = None, cost_usd: float | None = None) -> None:
        self.increment("llm_chat_turns_total")
        if latency_ms is not None:
            self.set_gauge("llm_chat_turn_latency_ms_last", latency_ms)
            self.observe("llm_chat_turn_latency_ms", latency_ms)
        if cost_usd is not None:
            self.set_gauge("llm_chat_turn_cost_usd_last", cost_usd)
            self.observe("llm_chat_turn_cost_usd", cost_usd)

    def render_prometheus(self) -> str:
        lines: list[str] = []
        for name, value in self._counters.items():
            metric_name = _sanitize_metric_name(name)
            lines.append(f"# TYPE {metric_name} counter")
            lines.append(f"{metric_name} {_format_number(value)}")
        for name, value in self._gauges.items():
            metric_name = _sanitize_metric_name(name)
            lines.append(f"# TYPE {metric_name} gauge")
            lines.append(f"{metric_name} {_format_number(value)}")
        for histogram in self._histograms.values():
            lines.extend(histogram.render())
        return "\n".join(lines) + "\n"
