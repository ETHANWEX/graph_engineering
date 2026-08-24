"""Secret-safe, bounded and failure-isolated telemetry implementation.

This module deliberately does not import an OpenTelemetry SDK.  It is the product boundary an SDK
adapter may implement; the deterministic exporter is sufficient for local contract evidence.
"""

from __future__ import annotations

import base64
import contextvars
import hashlib
import importlib
import json
import threading
import time
import urllib.parse
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any, Literal, Protocol, cast

from .types import AttributeValue, ExportResult, MetricRecord, SpanLink, SpanRecord, TelemetryRecord

CONTRACT_VERSION = "1.0"

SPAN_NAMES = frozenset(
    {
        "ge.runtime.run",
        "ge.runtime.node",
        "ge.runtime.parallel_branch",
        "ge.executor.invocation",
        "ge.verifier.execution",
        "ge.review.attempt",
        "ge.review.fix",
        "ge.service.operation",
        "ge.ipc.request",
        "ge.mcp.request",
        "ge.github.operation",
        "ge.report.generate",
        "ge.human.decision",
        "ge.runtime.recovery",
        "ge.runtime.cleanup",
    }
)

METRIC_NAMES = frozenset(
    {
        "ge.operation.duration",
        "ge.operation.result",
        "ge.operation.retry",
        "ge.budget.usage",
        "ge.queue.size",
        "ge.operations.active",
        "ge.telemetry.dropped",
        "ge.exporter.failure",
        "ge.exporter.duration",
    }
)

_ATTRIBUTE_KEYS = frozenset(
    {
        "ge.component",
        "ge.operation",
        "ge.result",
        "ge.action",
        "ge.reason",
        "ge.retryable",
        "ge.terminal",
        "ge.recovered",
        "ge.late",
        "ge.cleanup.state",
        "ge.provider",
        "ge.protocol.version",
        "ge.attempt.number",
        "ge.budget.calls",
        "ge.budget.cost",
        "ge.queue.capacity",
    }
)
_METRIC_LABEL_KEYS = frozenset(
    {
        "component",
        "operation",
        "result",
        "reason",
        "retryable",
        "provider",
        "protocol_version",
    }
)
_BOUNDED_VALUES: dict[str, frozenset[str]] = {
    "component": frozenset(
        {
            "runtime",
            "executor",
            "verifier",
            "review",
            "service",
            "ipc",
            "mcp",
            "github",
            "report",
            "human",
            "telemetry",
            "unknown",
        }
    ),
    "operation": frozenset(
        {
            "run",
            "node",
            "parallel_branch",
            "execute",
            "invoke",
            "recover",
            "cleanup",
            "review",
            "fix",
            "request",
            "initialize",
            "ping",
            "tools_list",
            "tools_call",
            "unknown",
            "invalid",
            "generate",
            "query",
            "checks_status",
            "pr_ensure",
            "pr_update",
            "decision",
            "start",
            "message",
            "confirm",
            "pause",
            "resume",
            "interrupt",
            "cancel",
            "accept",
            "reject",
            "revise",
            "status",
            "report",
            "health",
            "shutdown",
        }
    ),
    "result": frozenset(
        {
            "unknown",
            "success",
            "partial",
            "failure",
            "succeeded",
            "failed",
            "error",
            "passed",
            "pending",
            "running",
            "paused",
            "interrupted",
            "cancelled",
            "rejected",
            "blocked",
            "approved",
            "changes_requested",
            "complete",
            "completed",
        }
    ),
    "action": frozenset({"pause", "resume", "interrupt", "cancel", "accept", "reject", "revise"}),
    "reason": frozenset({"unknown", "barrier", "budget", "timeout", "overflow"}),
    "cleanup.state": frozenset({"unknown", "succeeded", "failed", "residual"}),
    "provider": frozenset({"unknown", "in_memory", "noop", "otlp"}),
    "protocol.version": frozenset({"1.0"}),
}
_SECRET_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)


class TelemetryDependencyMissing(RuntimeError):
    """An explicitly requested optional exporter module is unavailable."""


class ObservabilityCompatibilityError(RuntimeError):
    """A provider/exporter does not implement observability contract 1.0."""


class TelemetryExporter(Protocol):
    contract_version: str

    def export(
        self, records: Sequence[TelemetryRecord], timeout_seconds: float
    ) -> ExportResult: ...

    def shutdown(self, timeout_seconds: float) -> bool: ...


@dataclass(frozen=True)
class ObservabilityConfig:
    enabled: bool = False
    contract_version: str = CONTRACT_VERSION
    sampling_numerator: int = 1
    sampling_denominator: int = 1
    buffer_capacity: int = 1024
    batch_size: int = 128
    export_timeout_seconds: float = 1.0
    flush_timeout_seconds: float = 2.0
    shutdown_timeout_seconds: float = 2.0
    max_attribute_length: int = 256

    def __post_init__(self) -> None:
        if self.contract_version != CONTRACT_VERSION:
            raise ObservabilityCompatibilityError("observability contract version mismatch")
        if not 0 <= self.sampling_numerator <= self.sampling_denominator:
            raise ValueError("sampling numerator must be within the denominator")
        if self.sampling_denominator <= 0:
            raise ValueError("sampling denominator must be positive")
        if self.buffer_capacity <= 0 or not 0 < self.batch_size <= self.buffer_capacity:
            raise ValueError("telemetry buffer and batch bounds are invalid")
        if (
            min(
                self.export_timeout_seconds,
                self.flush_timeout_seconds,
                self.shutdown_timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("telemetry timeouts must be positive")
        if self.max_attribute_length <= 0:
            raise ValueError("max_attribute_length must be positive")


@dataclass(frozen=True)
class TelemetryIdentity:
    project_id: str | None = None
    repository_id: str | None = None
    run_id: str | None = None
    node_id: str | None = None
    attempt_id: str | None = None
    branch_id: str | None = None
    session_id: str | None = None
    verifier_id: str | None = None
    review_id: str | None = None
    external_effect_id: str | None = None
    provider_handle: str | None = None
    report_id: str | None = None
    artifact_id: str | None = None
    request_id: str | None = None

    def attributes(self) -> dict[str, str]:
        return {
            f"ge.{item.name.removesuffix('_id').replace('_', '.')}.id": value
            for item in fields(self)
            if (value := cast(str | None, getattr(self, item.name))) is not None
        }

    def trace_seed(self) -> str:
        values = (self.repository_id, self.project_id, self.run_id, self.request_id)
        return "\0".join(value for value in values if value) or "graph-engineering"

    def span_seed(self) -> str:
        return "\0".join(
            cast(str, getattr(self, item.name))
            for item in fields(self)
            if getattr(self, item.name) is not None
        )


@dataclass(frozen=True)
class TelemetryHealth:
    buffered: int
    dropped: int
    rejected: int
    export_failures: int
    export_timeouts: int
    partial_failures: int
    shutdown: bool


@dataclass(frozen=True)
class _SpanContext:
    trace_id: str
    span_id: str
    sampled: bool


_CURRENT: contextvars.ContextVar[_SpanContext | None] = contextvars.ContextVar(
    "graph_engineering_telemetry_context", default=None
)


class InMemoryExporter:
    """Thread-safe deterministic exporter for tests and local evidence."""

    contract_version = CONTRACT_VERSION

    def __init__(
        self,
        *,
        result: ExportResult | None = None,
        delay_seconds: float = 0,
        exception: bool = False,
    ) -> None:
        self.records: list[TelemetryRecord] = []
        self.result = result or ExportResult("success")
        self.delay_seconds = delay_seconds
        self.exception = exception
        self.closed = False
        self._lock = threading.Lock()

    def export(self, records: Sequence[TelemetryRecord], timeout_seconds: float) -> ExportResult:
        del timeout_seconds
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if self.exception:
            raise RuntimeError("exporter detail must never enter telemetry")
        accepted = self.result.accepted or len(records)
        if self.result.status != "failure":
            with self._lock:
                self.records.extend(records[:accepted])
        return ExportResult(self.result.status, min(accepted, len(records)))

    def shutdown(self, timeout_seconds: float) -> bool:
        del timeout_seconds
        self.closed = True
        return True


class TelemetrySpan:
    def __init__(
        self,
        provider: TelemetryProvider,
        name: str,
        identity: TelemetryIdentity,
        attributes: Mapping[str, AttributeValue],
        links: tuple[SpanLink, ...],
    ) -> None:
        self.provider = provider
        self.name = name
        self.identity = identity
        self.attributes = dict(attributes)
        self.links = links
        self.events: list[tuple[str, dict[str, AttributeValue]]] = []
        self.context: _SpanContext | None = None
        self.parent: _SpanContext | None = None
        self.started_ns = 0
        self._token: contextvars.Token[_SpanContext | None] | None = None

    def __enter__(self) -> TelemetrySpan:
        try:
            self.parent = _CURRENT.get()
            self.context = self.provider._context(self.name, self.identity, self.parent)
            self.started_ns = self.provider.clock_ns()
            if self.context.sampled:
                self._token = _CURRENT.set(self.context)
                self.provider._active_delta(self.name, 1, self.attributes)
        except Exception:
            self.provider._rejected += 1
            self.context = _SpanContext("", "", False)
        return self

    def set_result(self, result: str, *, terminal: bool | None = None) -> None:
        self.attributes["ge.result"] = result
        if terminal is not None:
            self.attributes["ge.terminal"] = terminal

    def add_identity(self, identity: TelemetryIdentity) -> None:
        """Attach a provider handle learned after an invocation starts."""

        self.attributes.update(identity.attributes())

    def add_event(self, name: str, attributes: Mapping[str, AttributeValue] | None = None) -> None:
        if name not in {"retry", "overflow", "cleanup", "recovered", "cancelled"}:
            self.provider._rejected += 1
            return
        self.events.append((name, dict(attributes or {})))

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> Literal[False]:
        del traceback
        if self.context is None or not self.context.sampled:
            return False
        try:
            end_ns = self.provider.clock_ns()
            if exc_type is not None:
                self.attributes["ge.result"] = "error"
            self.provider._finish_span(self, max(end_ns, self.started_ns))
            self.provider._active_delta(self.name, -1, self.attributes)
        except Exception:
            self.provider._rejected += 1
        finally:
            if self._token is not None:
                _CURRENT.reset(self._token)
        return False


class NoOpTelemetrySpan:
    context: _SpanContext | None = None

    def __enter__(self) -> NoOpTelemetrySpan:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> Literal[False]:
        return False

    def set_result(self, result: str, *, terminal: bool | None = None) -> None:
        del result, terminal

    def add_identity(self, identity: TelemetryIdentity) -> None:
        del identity

    def add_event(self, name: str, attributes: Mapping[str, AttributeValue] | None = None) -> None:
        del name, attributes


class TelemetryProvider:
    """Bounded telemetry recorder. All exporter failures are contained here."""

    contract_version = CONTRACT_VERSION

    def __init__(
        self,
        config: ObservabilityConfig,
        exporter: TelemetryExporter,
        *,
        secret_values: Sequence[str] = (),
        clock_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        if exporter.contract_version != CONTRACT_VERSION:
            raise ObservabilityCompatibilityError("exporter contract version mismatch")
        self.config = config
        self.exporter = exporter
        self.secret_values = tuple(value for value in secret_values if value)
        self.clock_ns = clock_ns
        self._buffer: deque[TelemetryRecord] = deque()
        self._lock = threading.RLock()
        self._sequence = 0
        self._dropped = 0
        self._rejected = 0
        self._export_failures = 0
        self._export_timeouts = 0
        self._partial_failures = 0
        self._shutdown = False
        self._terminal_runs: set[str] = set()
        self._active: dict[tuple[str, str], int] = {}
        self._last_export_duration = 0.0

    def span(
        self,
        name: str,
        identity: TelemetryIdentity | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        *,
        links: Sequence[SpanLink] = (),
    ) -> TelemetrySpan | NoOpTelemetrySpan:
        if not self.config.enabled or self._shutdown:
            return NoOpTelemetrySpan()
        if name not in SPAN_NAMES:
            self._rejected += 1
            return NoOpTelemetrySpan()
        identity = identity or TelemetryIdentity()
        values: dict[str, AttributeValue] = {**identity.attributes(), **dict(attributes or {})}
        if identity.run_id in self._terminal_runs:
            values["ge.late"] = True
        try:
            self.validate_attributes(values, identity_keys=True)
        except ValueError:
            self._rejected += 1
            return NoOpTelemetrySpan()
        return TelemetrySpan(self, name, identity, values, tuple(links))

    def metric(
        self,
        name: str,
        value: int | float,
        *,
        unit: str = "1",
        labels: Mapping[str, AttributeValue] | None = None,
    ) -> None:
        if not self.config.enabled or self._shutdown or name not in METRIC_NAMES:
            return
        checked = dict(labels or {})
        try:
            self.validate_metric_labels(checked)
        except ValueError:
            self._rejected += 1
            return
        self._enqueue(
            MetricRecord(
                sequence=self._next_sequence(),
                name=name,
                value=value,
                unit=unit,
                observed_ns=self.clock_ns(),
                labels=tuple(sorted(checked.items())),
            )
        )

    def mark_run_terminal(self, run_id: str) -> None:
        if run_id:
            self._terminal_runs.add(run_id)

    def link(self, identity: TelemetryIdentity, name: str = "identity") -> SpanLink:
        trace_id = _digest(identity.trace_seed(), 16)
        return SpanLink(trace_id, _digest(f"{trace_id}\0{name}\0{identity.span_seed()}", 8))

    def validate_attributes(
        self, values: Mapping[str, AttributeValue], *, identity_keys: bool = False
    ) -> None:
        for key, value in values.items():
            is_identity = key.startswith("ge.") and key.endswith(".id")
            if key not in _ATTRIBUTE_KEYS and not (identity_keys and is_identity):
                raise ValueError("telemetry attribute is not allowlisted")
            self._validate_value(key, value)
            bounded_key = key.removeprefix("ge.")
            if bounded_key in _BOUNDED_VALUES and str(value) not in _BOUNDED_VALUES[bounded_key]:
                raise ValueError("telemetry attribute value is not bounded")
        self._validate_cross_value_secrets(values.values())

    def validate_metric_labels(self, values: Mapping[str, AttributeValue]) -> None:
        for key, value in values.items():
            if key not in _METRIC_LABEL_KEYS:
                raise ValueError("metric label is not bounded")
            self._validate_value(key, value)
            if key in _BOUNDED_VALUES and str(value) not in _BOUNDED_VALUES[key]:
                raise ValueError("metric label value is not bounded")
        self._validate_cross_value_secrets(values.values())

    def force_flush(self, timeout_seconds: float | None = None) -> bool:
        self._emit_health_metrics()
        deadline = time.monotonic() + (timeout_seconds or self.config.flush_timeout_seconds)
        success = True
        while True:
            with self._lock:
                if not self._buffer:
                    return success
                batch = tuple(list(self._buffer)[: self.config.batch_size])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._export_timeouts += 1
                return False
            status = self._export(batch, min(remaining, self.config.export_timeout_seconds))
            if status is None:
                return False
            accepted = len(batch) if status.status == "success" else status.accepted
            with self._lock:
                for _ in range(min(accepted, len(self._buffer))):
                    self._buffer.popleft()
            if status.status != "success":
                success = False
                if accepted == 0:
                    return False

    def shutdown(self, timeout_seconds: float | None = None) -> bool:
        timeout = timeout_seconds or self.config.shutdown_timeout_seconds
        flushed = self.force_flush(timeout)
        closed = self._call_with_timeout(lambda: self.exporter.shutdown(timeout), timeout)
        self._shutdown = True
        return flushed and closed is True

    def health(self) -> TelemetryHealth:
        with self._lock:
            return TelemetryHealth(
                buffered=len(self._buffer),
                dropped=self._dropped,
                rejected=self._rejected,
                export_failures=self._export_failures,
                export_timeouts=self._export_timeouts,
                partial_failures=self._partial_failures,
                shutdown=self._shutdown,
            )

    def _context(
        self, name: str, identity: TelemetryIdentity, parent: _SpanContext | None
    ) -> _SpanContext:
        trace_id = parent.trace_id if parent is not None else _digest(identity.trace_seed(), 16)
        sampled = parent.sampled if parent is not None else self._sample(trace_id)
        span_id = _digest(f"{trace_id}\0{name}\0{identity.span_seed()}\0{self._sequence + 1}", 8)
        return _SpanContext(trace_id, span_id, sampled)

    def _sample(self, trace_id: str) -> bool:
        if self.config.sampling_numerator == 0:
            return False
        bucket = int(trace_id[:16], 16) % self.config.sampling_denominator
        return bucket < self.config.sampling_numerator

    def _finish_span(self, span: TelemetrySpan, end_ns: int) -> None:
        assert span.context is not None
        try:
            self.validate_attributes(span.attributes, identity_keys=True)
            events = []
            for name, attributes in span.events:
                self.validate_attributes(attributes)
                events.append((name, tuple(sorted(attributes.items()))))
        except ValueError:
            self._rejected += 1
            return
        self._enqueue(
            SpanRecord(
                sequence=self._next_sequence(),
                name=span.name,
                trace_id=span.context.trace_id,
                span_id=span.context.span_id,
                parent_span_id=span.parent.span_id if span.parent is not None else None,
                links=span.links,
                start_ns=span.started_ns,
                end_ns=end_ns,
                attributes=tuple(sorted(span.attributes.items())),
                events=tuple(events),
            )
        )
        self.metric(
            "ge.operation.duration",
            max(0, end_ns - span.started_ns) / 1_000_000_000,
            unit="s",
            labels={
                "component": str(span.attributes.get("ge.component", "unknown")),
                "operation": str(span.attributes.get("ge.operation", "unknown")),
                "result": str(span.attributes.get("ge.result", "unknown")),
            },
        )
        self.metric(
            "ge.operation.result",
            1,
            labels={
                "component": str(span.attributes.get("ge.component", "unknown")),
                "operation": str(span.attributes.get("ge.operation", "unknown")),
                "result": str(span.attributes.get("ge.result", "unknown")),
            },
        )

    def _active_delta(
        self, name: str, delta: int, attributes: Mapping[str, AttributeValue]
    ) -> None:
        component = name.split(".")[1] if "." in name else "unknown"
        operation = str(attributes.get("ge.operation", name.rsplit(".", 1)[-1]))
        key = (component, operation)
        with self._lock:
            self._active[key] = max(0, self._active.get(key, 0) + delta)
            active = self._active[key]
        self.metric(
            "ge.operations.active",
            active,
            labels={"component": component, "operation": operation},
        )

    def _enqueue(self, record: TelemetryRecord) -> None:
        with self._lock:
            if len(self._buffer) >= self.config.buffer_capacity:
                self._dropped += 1
                return
            self._buffer.append(record)

    def _next_sequence(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def _export(self, batch: Sequence[TelemetryRecord], timeout: float) -> ExportResult | None:
        started = time.monotonic()
        result = self._call_with_timeout(lambda: self.exporter.export(batch, timeout), timeout)
        self._last_export_duration = time.monotonic() - started
        if result is None:
            return None
        if not isinstance(result, ExportResult):
            self._export_failures += 1
            return None
        if result.status == "failure":
            self._export_failures += 1
        elif result.status == "partial":
            self._partial_failures += 1
        return result

    def _call_with_timeout(self, call: Callable[[], Any], timeout: float) -> Any | None:
        completed = threading.Event()
        result: list[Any] = []

        def invoke() -> None:
            try:
                result.append(call())
            except Exception:
                result.append(None)
            finally:
                completed.set()

        worker = threading.Thread(target=invoke, name="ge-telemetry-export", daemon=True)
        worker.start()
        if not completed.wait(timeout):
            self._export_timeouts += 1
            return None
        if not result or result[0] is None:
            self._export_failures += 1
            return None
        return result[0]

    def _emit_health_metrics(self) -> None:
        labels = {"component": "telemetry", "operation": "unknown"}
        self.metric("ge.queue.size", len(self._buffer), labels=labels)
        self.metric("ge.telemetry.dropped", self._dropped, labels=labels)
        self.metric("ge.exporter.failure", self._export_failures, labels=labels)
        self.metric(
            "ge.exporter.duration",
            self._last_export_duration,
            unit="s",
            labels={**labels, "result": "unknown"},
        )

    def _validate_value(self, key: str, value: AttributeValue) -> None:
        if any(part in key.casefold() for part in _SECRET_KEY_PARTS):
            raise ValueError("secret-bearing telemetry key is forbidden")
        text = str(value)
        if len(text) > self.config.max_attribute_length:
            raise ValueError("telemetry value exceeded its bound")
        lowered = text.casefold()
        if any(marker in lowered for marker in ("http://", "https://", "file://", "\\", "/")):
            raise ValueError("path or endpoint telemetry value is forbidden")
        serialized = json.dumps(value, ensure_ascii=False)
        for secret in self.secret_values:
            forms = {
                secret,
                urllib.parse.quote(secret, safe=""),
                base64.b64encode(secret.encode()).decode(),
            }
            if any(form and form in serialized for form in forms):
                raise ValueError("secret value is forbidden in telemetry")

    def _validate_cross_value_secrets(self, values: Any) -> None:
        combined = "".join(str(value) for value in values)
        for secret in self.secret_values:
            forms = (
                secret,
                urllib.parse.quote(secret, safe=""),
                base64.b64encode(secret.encode()).decode(),
            )
            if any(form and form in combined for form in forms):
                raise ValueError("cross-value secret is forbidden in telemetry")


class NoOpTelemetryProvider(TelemetryProvider):
    def __init__(self) -> None:
        super().__init__(ObservabilityConfig(enabled=False), InMemoryExporter())


def load_optional_exporter(module_name: str, factory_name: str = "create_exporter") -> Any:
    """Load an explicitly requested optional adapter with typed import/compatibility behavior."""

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise TelemetryDependencyMissing(
            "optional telemetry exporter dependency is unavailable"
        ) from exc
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise ObservabilityCompatibilityError("optional exporter factory is incompatible")
    exporter = factory()
    if getattr(exporter, "contract_version", None) != CONTRACT_VERSION:
        raise ObservabilityCompatibilityError("optional exporter contract version mismatch")
    return exporter


def safe_telemetry_provider(
    config: ObservabilityConfig,
    exporter_factory: Callable[[], TelemetryExporter],
    *,
    secret_values: Sequence[str] = (),
) -> TelemetryProvider:
    """Create an enabled provider or fail safely to a disabled provider.

    Callers that need diagnostic classification can call ``load_optional_exporter`` first and
    retain its typed exception outside product execution.
    """

    if not config.enabled:
        return NoOpTelemetryProvider()
    try:
        return TelemetryProvider(config, exporter_factory(), secret_values=secret_values)
    except Exception:
        return NoOpTelemetryProvider()


def _digest(value: str, bytes_count: int) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[: bytes_count * 2]
