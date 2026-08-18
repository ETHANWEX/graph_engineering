"""Bridge natural-language queries to the Phase 2 fresh read-only Observer."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from graph_engineering.executor import ExecutorRequest, ExecutorRole, SandboxMode
from graph_engineering.models import QueryControlIntent
from graph_engineering.review import ReadOnlyRoleRunner


class Phase2Observer:
    def __init__(
        self,
        runner: ReadOnlyRoleRunner,
        request_factory: Callable[[QueryControlIntent], ExecutorRequest],
    ) -> None:
        self.runner = runner
        self.request_factory = request_factory

    def __call__(self, intent: QueryControlIntent) -> Any:
        request = self.request_factory(intent)
        if (
            request.role is not ExecutorRole.OBSERVER
            or request.sandbox is not SandboxMode.READ_ONLY
        ):
            raise ValueError("natural-language queries require a fresh read-only Observer request")
        return self.runner.observe(request)
