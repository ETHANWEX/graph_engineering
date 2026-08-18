"""Fresh read-only role calls with Observer non-interference enforcement."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from graph_engineering.executor import ExecutorRequest, ExecutorRole, SandboxMode


class RoleExecutor(Protocol):
    def review(self, request: ExecutorRequest) -> Any: ...

    def start(self, request: ExecutorRequest) -> Any: ...


class RoleIsolationError(RuntimeError):
    pass


class ObserverFailure(RuntimeError):
    pass


class ReadOnlyRoleRunner:
    def __init__(self, executor: RoleExecutor, *, fingerprint: Callable[[], object]) -> None:
        self.executor = executor
        self.fingerprint = fingerprint
        self._attempts: set[str] = set()

    def review(self, request: ExecutorRequest) -> Any:
        self._validate_fresh_readonly(request, ExecutorRole.REVIEWER)
        return self.executor.review(request)

    def observe(self, request: ExecutorRequest) -> Any:
        self._validate_fresh_readonly(request, ExecutorRole.OBSERVER)
        before = self.fingerprint()
        try:
            result = self.executor.start(request)
        except Exception as exc:
            if self.fingerprint() != before:
                raise RoleIsolationError("Observer failure mutated main Run state") from exc
            raise ObserverFailure(str(exc)) from exc
        if self.fingerprint() != before:
            raise RoleIsolationError("Observer mutated main Run state")
        return result

    def _validate_fresh_readonly(
        self, request: ExecutorRequest, expected_role: ExecutorRole
    ) -> None:
        if request.role is not expected_role or request.sandbox is not SandboxMode.READ_ONLY:
            raise RoleIsolationError(f"{expected_role.value} must use a read-only request")
        if request.attempt_id in self._attempts:
            raise RoleIsolationError("read-only role attempts must use a fresh Session")
        self._attempts.add(request.attempt_id)
