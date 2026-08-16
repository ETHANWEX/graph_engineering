"""Durable invocation policy layered over a provider-neutral Executor."""

from __future__ import annotations

from graph_engineering.models.results import ExecutorStatus

from .types import (
    ExecutorOutcome,
    ExecutorProtocol,
    ExecutorRequest,
    ExecutorRole,
    SessionHandle,
    SessionPolicy,
)


class ExecutionBarrierError(RuntimeError):
    pass


class DurableExecutorRuntime:
    def __init__(
        self,
        executor: ExecutorProtocol,
        sessions: object,
        policy: SessionPolicy | None = None,
    ) -> None:
        self.executor = executor
        self.sessions = sessions
        self.policy = policy or SessionPolicy()

    def execute(self, request: ExecutorRequest) -> ExecutorOutcome:
        from graph_engineering.runtime.sessions import SessionRepository

        if not isinstance(self.sessions, SessionRepository):
            raise TypeError("sessions must be a SessionRepository")
        persisted = self.sessions.completed_outcome(request.run_id, request.attempt_id)
        if persisted is not None:
            return persisted
        self._check_barrier(request.run_id)
        latest = self.sessions.latest(request.run_id, request.node_id)
        should_resume = (
            latest is not None
            and self.policy.allows_resume(request.role, same_node=True)
            and not self.policy.should_rotate(latest)
        )
        if should_resume and latest is not None:
            outcome = self.executor.resume(
                SessionHandle(latest.provider, latest.provider_session_id, latest.provider_version),
                request,
            )
            continuation_count = latest.continuation_count + 1
            inherited_failures = latest.failure_count
        else:
            if latest is not None and self.policy.should_rotate(latest):
                self.sessions.rotate(latest.session_id)
            outcome = (
                self.executor.review(request)
                if request.role is ExecutorRole.REVIEWER
                else self.executor.start(request)
            )
            continuation_count = 0
            inherited_failures = 0
        record = self.sessions.start(
            request.run_id,
            request.node_id,
            request.attempt_id,
            request.role,
            outcome.session.provider,
            outcome.session.provider_session_id,
            outcome.session.provider_version,
            continuation_count=continuation_count,
            failure_count=inherited_failures,
        )
        if outcome.result.status in {ExecutorStatus.FAILED, ExecutorStatus.ERROR}:
            self.sessions.record_failure(record.session_id)
        self.sessions.complete(
            record.session_id,
            stdout_artifact_id=outcome.raw_stdout.artifact_id,
            stderr_artifact_id=(
                outcome.raw_stderr.artifact_id if outcome.raw_stderr is not None else None
            ),
            outcome=outcome,
        )
        return outcome

    def cancel(self, run_id: str, node_id: str, *, grace_seconds: float = 5) -> bool:
        from graph_engineering.runtime.sessions import SessionRepository

        if not isinstance(self.sessions, SessionRepository):
            raise TypeError("sessions must be a SessionRepository")
        latest = self.sessions.latest(run_id, node_id)
        if latest is None:
            return True
        self.sessions.request_cancel(latest.session_id)
        terminated = self.executor.cancel(
            SessionHandle(latest.provider, latest.provider_session_id, latest.provider_version),
            grace_seconds=grace_seconds,
        )
        self.sessions.settle_cancel(latest.session_id, terminated=terminated)
        return terminated

    def _check_barrier(self, run_id: str) -> None:
        from graph_engineering.runtime.sessions import SessionRepository

        assert isinstance(self.sessions, SessionRepository)
        with self.sessions.state.read_connection() as connection:
            row = connection.execute(
                "SELECT status, barrier FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is not None and (row["barrier"] is not None or str(row["status"]) != "running"):
            raise ExecutionBarrierError("persisted Run barrier forbids a new Executor Session")
