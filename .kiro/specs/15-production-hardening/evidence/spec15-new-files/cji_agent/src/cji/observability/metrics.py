"""
Process metrics in Prometheus text format 0.0.4 (Spec 15, OD-160). Standard library only.

Every series is declared once with fixed label names. Label values must come from closed sets (route templates,
status codes, enum values): `_label()` rejects anything else that looks like user input, so a client cannot create
unbounded series. One registry per process; counters reset when the process restarts.
"""

from __future__ import annotations

import math
import re
import threading
from collections.abc import Iterable

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
DEFAULT_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
_NAME = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")
_LABEL_VALUE = re.compile(r"[A-Za-z0-9_./{}:\- ]{0,120}")
MAX_SERIES_PER_METRIC = 500


def _label(value: object) -> str:
    text = str(value)
    if not _LABEL_VALUE.fullmatch(text):
        return "invalid"
    return text


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _num(value: float) -> str:
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


class _Metric:
    kind = ""

    def __init__(self, name: str, help_text: str, labels: Iterable[str] = ()) -> None:
        if not _NAME.fullmatch(name):
            raise ValueError(f"invalid metric name: {name}")
        self.name = name
        self.help = help_text
        self.labels = tuple(labels)
        self._lock = threading.Lock()

    def _key(self, values: dict[str, object]) -> tuple[str, ...]:
        if set(values) != set(self.labels):
            raise ValueError(f"{self.name} takes labels {self.labels}, got {sorted(values)}")
        return tuple(_label(values[name]) for name in self.labels)

    def _labels_text(self, key: tuple[str, ...], extra: tuple[tuple[str, str], ...] = ()) -> str:
        pairs = [*zip(self.labels, key, strict=True), *extra]
        if not pairs:
            return ""
        return "{" + ",".join(f'{n}="{_escape(v)}"' for n, v in pairs) + "}"

    def header(self) -> list[str]:
        return [f"# HELP {self.name} {_escape(self.help)}", f"# TYPE {self.name} {self.kind}"]

    def render(self) -> list[str]:
        raise NotImplementedError


class Counter(_Metric):
    kind = "counter"

    def __init__(self, name: str, help_text: str, labels: Iterable[str] = ()) -> None:
        super().__init__(name, help_text, labels)
        self._values: dict[tuple[str, ...], float] = {}

    def inc(self, amount: float = 1.0, **labels: object) -> None:
        if amount < 0:
            raise ValueError("counters only go up")
        key = self._key(labels)
        with self._lock:
            if key not in self._values and len(self._values) >= MAX_SERIES_PER_METRIC:
                key = tuple("overflow" for _ in self.labels)
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **labels: object) -> float:
        with self._lock:
            return self._values.get(self._key(labels), 0.0)

    def render(self) -> list[str]:
        with self._lock:
            items = sorted(self._values.items())
        return [*self.header(), *(f"{self.name}{self._labels_text(k)} {_num(v)}" for k, v in items)]


class Gauge(Counter):
    kind = "gauge"

    def set(self, value: float, **labels: object) -> None:
        key = self._key(labels)
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0, **labels: object) -> None:
        key = self._key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, **labels: object) -> None:
        self.inc(-amount, **labels)


class Histogram(_Metric):
    kind = "histogram"

    def __init__(
        self, name: str, help_text: str, labels: Iterable[str] = (), buckets: tuple[float, ...] = DEFAULT_BUCKETS
    ) -> None:
        super().__init__(name, help_text, labels)
        self.buckets = tuple(sorted(buckets))
        self._series: dict[tuple[str, ...], tuple[list[int], list[float]]] = {}

    def observe(self, value: float, **labels: object) -> None:
        key = self._key(labels)
        with self._lock:
            if key not in self._series and len(self._series) >= MAX_SERIES_PER_METRIC:
                key = tuple("overflow" for _ in self.labels)
            counts, totals = self._series.setdefault(key, ([0] * (len(self.buckets) + 1), [0.0]))
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    counts[i] += 1
            counts[-1] += 1
            totals[0] += value

    def render(self) -> list[str]:
        lines = self.header()
        with self._lock:
            items = sorted((k, (list(c), t[0])) for k, (c, t) in self._series.items())
        for key, (counts, total) in items:
            for bound, count in zip((*self.buckets, math.inf), counts, strict=True):
                lines.append(f"{self.name}_bucket{self._labels_text(key, (('le', _num(bound)),))} {count}")
            lines.append(f"{self.name}_sum{self._labels_text(key)} {_num(total)}")
            lines.append(f"{self.name}_count{self._labels_text(key)} {counts[-1]}")
        return lines


class Registry:
    def __init__(self) -> None:
        self._metrics: dict[str, _Metric] = {}
        self._lock = threading.Lock()

    def _add(self, metric: _Metric) -> _Metric:
        with self._lock:
            existing = self._metrics.get(metric.name)
            if existing is not None:
                if type(existing) is not type(metric) or existing.labels != metric.labels:
                    raise ValueError(f"metric {metric.name} already registered differently")
                return existing
            self._metrics[metric.name] = metric
            return metric

    def counter(self, name: str, help_text: str, labels: Iterable[str] = ()) -> Counter:
        metric = self._add(Counter(name, help_text, labels))
        assert isinstance(metric, Counter)  # nosec B101 - type narrowing after a checked registration
        return metric

    def gauge(self, name: str, help_text: str, labels: Iterable[str] = ()) -> Gauge:
        metric = self._add(Gauge(name, help_text, labels))
        assert isinstance(metric, Gauge)  # nosec B101 - type narrowing after a checked registration
        return metric

    def histogram(
        self, name: str, help_text: str, labels: Iterable[str] = (), buckets: tuple[float, ...] = DEFAULT_BUCKETS
    ) -> Histogram:
        metric = self._add(Histogram(name, help_text, labels, buckets))
        assert isinstance(metric, Histogram)  # nosec B101 - type narrowing after a checked registration
        return metric

    def render(self) -> str:
        with self._lock:
            metrics = sorted(self._metrics.values(), key=lambda m: m.name)
        return "\n".join(line for metric in metrics for line in metric.render()) + "\n"


REGISTRY = Registry()

# Series (design §4). Declared here so every process exposes the same names; each process fills its own.
HTTP_REQUESTS = REGISTRY.counter(
    "cji_http_requests_total",
    "HTTP requests by route template, method and status.",
    ("service", "route", "method", "status"),
)
HTTP_SECONDS = REGISTRY.histogram("cji_http_request_seconds", "HTTP request duration in seconds.", ("service", "route"))
RATE_LIMITED = REGISTRY.counter(
    "cji_rate_limited_total", "Requests rejected by a rate limiter.", ("service", "limiter")
)
AUTH_FAILURES = REGISTRY.counter("cji_auth_failures_total", "Failed API authentications by reason.", ("reason",))
RUNS_ACTIVE = REGISTRY.gauge("cji_runs_active", "Runs driven by this API process now.")
RUNS_FINISHED = REGISTRY.counter(
    "cji_runs_finished_total", "Runs driven by this API process, by final status.", ("status",)
)
TOOL_CALLS = REGISTRY.counter(
    "cji_tool_calls_total", "MCP tool calls by service, tool and outcome.", ("service", "tool", "outcome")
)
LLM_CALLS = REGISTRY.counter("cji_llm_calls_total", "LLM calls by provider and outcome.", ("provider", "outcome"))
LLM_TOKENS = REGISTRY.counter("cji_llm_tokens_total", "LLM tokens by direction.", ("direction",))
LLM_COST = REGISTRY.counter("cji_llm_cost_usd_total", "LLM cost in USD (only when prices are configured).")
COLLECTOR_EVENTS = REGISTRY.counter("cji_collector_events_total", "Collected events by outcome.", ("outcome",))
INGESTION_ROWS = REGISTRY.counter(
    "cji_ingestion_rows_total", "Rows written by API ingestions, by write mode.", ("mode",)
)
