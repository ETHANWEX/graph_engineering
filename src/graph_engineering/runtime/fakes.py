"""Deterministic Phase 1 Executor and Verifier test doubles."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from graph_engineering.models.graph import Node
from graph_engineering.models.results import (
    ExecutorResult,
    ExecutorStatus,
    VerifierResult,
    VerifierStatus,
)


@dataclass(frozen=True)
class FakeCall:
    run_id: str
    node_id: str
    attempt_id: str
    idempotency_key: str | None = None


class FakeExecutor:
    def __init__(self, scripts: dict[str, list[ExecutorResult]] | None = None) -> None:
        self._scripts = {key: list(values) for key, values in (scripts or {}).items()}
        self.calls: list[FakeCall] = []
        self._lock = threading.Lock()
        self.after_execute: Callable[[FakeCall], object] | None = None

    def execute(self, run_id: str, node: Node, attempt_id: str) -> ExecutorResult:
        call = FakeCall(run_id=run_id, node_id=node.node_id, attempt_id=attempt_id)
        with self._lock:
            self.calls.append(call)
            values = self._scripts.get(node.node_id)
            if not values:
                raise RuntimeError(f"no Fake Executor result scripted for {node.node_id}")
            result = values.pop(0)
        if self.after_execute is not None:
            self.after_execute(call)
        return result


class FakeVerifier:
    def __init__(
        self,
        scripts: dict[str, list[VerifierResult]] | None = None,
        *,
        query_results: dict[str, list[VerifierResult]] | None = None,
    ) -> None:
        self._scripts = {key: list(values) for key, values in (scripts or {}).items()}
        self._query_results = {key: list(values) for key, values in (query_results or {}).items()}
        self.calls: list[FakeCall] = []
        self._lock = threading.Lock()
        self.trigger_count = 0
        self.query_count = 0
        self.after_execute: Callable[[FakeCall], object] | None = None

    def execute(
        self,
        run_id: str,
        node: Node,
        attempt_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> VerifierResult:
        call = FakeCall(run_id, node.node_id, attempt_id, idempotency_key)
        with self._lock:
            self.calls.append(call)
            if idempotency_key is not None:
                self.trigger_count += 1
            values = self._scripts.get(node.node_id)
            if not values:
                raise RuntimeError(f"no Fake Verifier result scripted for {node.node_id}")
            result = values.pop(0)
        if self.after_execute is not None:
            self.after_execute(call)
        return result

    def query(self, handle: str) -> VerifierResult:
        self.query_count += 1
        values = self._query_results.get(handle)
        if not values:
            return VerifierResult(
                schema_version="1.0",
                status=VerifierStatus.PENDING,
                summary="still pending",
                external_handle=handle,
            )
        return values.pop(0)


def executor_error(message: str) -> ExecutorResult:
    return ExecutorResult(
        schema_version="1.0", status=ExecutorStatus.FAILED, summary=message, failure_reason=message
    )
