"""Queryable subprocess handles with bounded termination."""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessHandle:
    handle_id: str
    process_id: int
    process: subprocess.Popen[bytes]


@dataclass(frozen=True)
class ProcessState:
    running: bool
    return_code: int | None


@dataclass(frozen=True)
class CancellationResult:
    requested: bool
    terminated: bool
    quiescing: bool
    return_code: int | None


class ProcessSupervisor:
    def __init__(self) -> None:
        self._handles: dict[str, ProcessHandle] = {}

    def start(self, argv: list[str], *, cwd: Path) -> ProcessHandle:
        if not argv:
            raise ValueError("argv must not be empty")
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        handle = ProcessHandle(f"process:{uuid.uuid4()}", process.pid, process)
        self._handles[handle.handle_id] = handle
        return handle

    def query(self, handle: ProcessHandle) -> ProcessState:
        return ProcessState(handle.process.poll() is None, handle.process.returncode)

    def cancel(self, handle: ProcessHandle, *, grace_seconds: float = 5) -> CancellationResult:
        state = self.query(handle)
        if not state.running:
            return CancellationResult(False, True, False, state.return_code)
        handle.process.terminate()
        terminated = self._wait(handle.process, grace_seconds)
        return CancellationResult(True, terminated, not terminated, handle.process.returncode)

    @staticmethod
    def _wait(process: subprocess.Popen[bytes], timeout: float) -> bool:
        try:
            process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False
