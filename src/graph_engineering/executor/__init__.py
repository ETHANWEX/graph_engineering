"""Provider-neutral execution contracts used by Runtime and adapters."""

from .process import CancellationResult, ProcessHandle, ProcessState, ProcessSupervisor
from .runtime import DurableExecutorRuntime, ExecutionBarrierError
from .types import (
    ExecutorCapabilities,
    ExecutorEvent,
    ExecutorOutcome,
    ExecutorProtocol,
    ExecutorRequest,
    ExecutorRole,
    SandboxMode,
    SessionHandle,
    SessionPolicy,
    SessionRecord,
    SessionStatus,
)

__all__ = [
    "CancellationResult",
    "DurableExecutorRuntime",
    "ExecutionBarrierError",
    "ExecutorCapabilities",
    "ExecutorEvent",
    "ExecutorOutcome",
    "ExecutorProtocol",
    "ExecutorRequest",
    "ExecutorRole",
    "ProcessHandle",
    "ProcessState",
    "ProcessSupervisor",
    "SandboxMode",
    "SessionHandle",
    "SessionPolicy",
    "SessionRecord",
    "SessionStatus",
]
