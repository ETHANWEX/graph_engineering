"""Stable internal Executor types; no provider event payload is authoritative state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from graph_engineering.models import Artifact, ExecutorResult


class ExecutorRole(StrEnum):
    IMPLEMENTER = "implementer"
    REVIEWER = "reviewer"
    OBSERVER = "observer"


class SandboxMode(StrEnum):
    WORKSPACE_WRITE = "workspace-write"
    READ_ONLY = "read-only"


class SessionStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    QUIESCING = "quiescing"
    ROTATED = "rotated"


@dataclass(frozen=True)
class ExecutorCapabilities:
    provider: str
    version: str
    authenticated: bool
    json_events: bool
    output_schema: bool
    output_last_message: bool
    resume: bool
    review: bool
    workspace_write: bool
    read_only: bool
    approval_never: bool
    process_cancel: bool = True

    @property
    def supports_required_phase2(self) -> bool:
        return self.authenticated and all(
            (
                self.json_events,
                self.output_schema,
                self.output_last_message,
                self.resume,
                self.review,
                self.workspace_write,
                self.read_only,
                self.approval_never,
                self.process_cancel,
            )
        )


@dataclass(frozen=True)
class ExecutorRequest:
    run_id: str
    node_id: str
    attempt_id: str
    role: ExecutorRole
    objective: str
    context: str
    working_directory: Path
    sandbox: SandboxMode
    output_schema: dict[str, object]
    control_directory: Path
    timeout_seconds: float = 1800

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise ValueError("objective must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if (
            self.role in {ExecutorRole.REVIEWER, ExecutorRole.OBSERVER}
            and self.sandbox is not SandboxMode.READ_ONLY
        ):
            raise ValueError("reviewer and observer requests must be read-only")


@dataclass(frozen=True)
class SessionHandle:
    provider: str
    provider_session_id: str
    provider_version: str


@dataclass(frozen=True)
class ExecutorEvent:
    event_type: str
    provider_event_type: str | None
    session_id: str | None
    data: dict[str, object]


@dataclass(frozen=True)
class ExecutorOutcome:
    session: SessionHandle
    result: ExecutorResult
    events: tuple[ExecutorEvent, ...]
    raw_stdout: Artifact
    raw_stderr: Artifact | None
    exit_code: int


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    run_id: str
    node_id: str
    attempt_id: str
    role: ExecutorRole
    provider: str
    provider_session_id: str
    provider_version: str
    status: SessionStatus
    continuation_count: int
    failure_count: int
    process_id: int | None = None


@dataclass(frozen=True)
class SessionPolicy:
    max_continuations: int = 2
    rotate_after_failures: int = 2

    def allows_resume(self, role: ExecutorRole, *, same_node: bool) -> bool:
        return role is ExecutorRole.IMPLEMENTER and same_node

    def should_rotate(self, session: SessionRecord) -> bool:
        return (
            session.continuation_count >= self.max_continuations
            or session.failure_count >= self.rotate_after_failures
            or session.role is not ExecutorRole.IMPLEMENTER
        )


class ExecutorProtocol(Protocol):
    def capabilities(self) -> ExecutorCapabilities: ...

    def start(self, request: ExecutorRequest) -> ExecutorOutcome: ...

    def resume(self, session: SessionHandle, request: ExecutorRequest) -> ExecutorOutcome: ...

    def review(self, request: ExecutorRequest) -> ExecutorOutcome: ...

    def cancel(self, session: SessionHandle, *, grace_seconds: float = 5) -> bool: ...
