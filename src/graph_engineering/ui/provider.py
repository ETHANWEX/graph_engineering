"""Narrow Runtime Service provider used by the optional UI."""

from __future__ import annotations

from typing import Any, Protocol

from graph_engineering.service import ServiceClient


class UIProvider(Protocol):
    def project_snapshot(self) -> dict[str, Any]: ...

    def run_snapshot(self, run_id: str) -> dict[str, Any]: ...

    def mutate(
        self,
        operation: str,
        payload: dict[str, object],
        *,
        request_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]: ...


class RuntimeServiceUIProvider:
    """Calls IPC only; this class never opens SQLite or a worktree."""

    def __init__(self, client: ServiceClient) -> None:
        self.client = client

    def project_snapshot(self) -> dict[str, Any]:
        return self.client.call("project_snapshot")

    def run_snapshot(self, run_id: str) -> dict[str, Any]:
        return self.client.call("run_snapshot", {"run_id": run_id})

    def mutate(
        self,
        operation: str,
        payload: dict[str, object],
        *,
        request_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self.client.call(
            operation,
            payload,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
