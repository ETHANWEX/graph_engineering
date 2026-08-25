"""Immutable exporter records for observability contract 1.0."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

type AttributeValue = str | bool | int | float


@dataclass(frozen=True)
class SpanLink:
    trace_id: str
    span_id: str


@dataclass(frozen=True)
class SpanRecord:
    sequence: int
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    links: tuple[SpanLink, ...]
    start_ns: int
    end_ns: int
    attributes: tuple[tuple[str, AttributeValue], ...]
    events: tuple[tuple[str, tuple[tuple[str, AttributeValue], ...]], ...]


@dataclass(frozen=True)
class MetricRecord:
    sequence: int
    name: str
    value: int | float
    unit: str
    observed_ns: int
    labels: tuple[tuple[str, AttributeValue], ...]


type TelemetryRecord = SpanRecord | MetricRecord


@dataclass(frozen=True)
class ExportResult:
    status: Literal["success", "partial", "failure"]
    accepted: int = 0
