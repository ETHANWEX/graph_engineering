"""Optional, non-authoritative observability provider boundary."""

from .provider import (
    InMemoryExporter,
    NoOpTelemetryProvider,
    ObservabilityCompatibilityError,
    ObservabilityConfig,
    TelemetryDependencyMissing,
    TelemetryHealth,
    TelemetryIdentity,
    TelemetryProvider,
    TelemetrySpan,
    load_optional_exporter,
    safe_telemetry_provider,
)
from .types import ExportResult, MetricRecord, SpanLink, SpanRecord, TelemetryRecord

__all__ = [
    "ExportResult",
    "InMemoryExporter",
    "MetricRecord",
    "NoOpTelemetryProvider",
    "ObservabilityCompatibilityError",
    "ObservabilityConfig",
    "SpanLink",
    "SpanRecord",
    "TelemetryDependencyMissing",
    "TelemetryHealth",
    "TelemetryIdentity",
    "TelemetryProvider",
    "TelemetryRecord",
    "TelemetrySpan",
    "load_optional_exporter",
    "safe_telemetry_provider",
]
