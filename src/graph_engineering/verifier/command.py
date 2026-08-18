"""Declaration-only subprocess verifier with bounded time and evidence."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from graph_engineering.models import Artifact, Error, VerifierResult
from graph_engineering.models.common import ArtifactKind, ErrorKind
from graph_engineering.models.results import VerifierStatus
from graph_engineering.runtime.artifacts import ArtifactStore


@dataclass(frozen=True)
class CommandVerifierSpec:
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: float = 300
    max_output_bytes: int = 1024 * 1024
    environment: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.argv or not self.argv[0].strip():
            raise ValueError("argv must contain an executable")
        if any(token in self.argv[0] for token in ("&&", "||", ";", "|", "\n", "\r")):
            raise ValueError("argv executable must not contain shell source")
        if self.timeout_seconds <= 0 or self.max_output_bytes <= 0:
            raise ValueError("timeout and output limits must be positive")


@dataclass(frozen=True)
class CommandVerifierOutcome:
    result: VerifierResult
    stdout_artifact: Artifact | None
    stderr_artifact: Artifact | None
    exit_code: int | None


class VerificationBarrierError(RuntimeError):
    pass


class CommandVerifier:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        *,
        can_start: Callable[[], bool] | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.can_start = can_start or (lambda: True)

    def run(self, spec: CommandVerifierSpec) -> CommandVerifierOutcome:
        if not self.can_start():
            raise VerificationBarrierError("persisted Run barrier forbids a new Command Verifier")
        try:
            completed = subprocess.run(
                list(spec.argv),
                cwd=spec.cwd,
                env=dict(spec.environment) or None,
                capture_output=True,
                check=False,
                timeout=spec.timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._bytes(exc.stdout)
            stderr = self._bytes(exc.stderr)
            return self._error(
                "command.timeout", "command verifier timed out", stdout, stderr, None
            )
        except OSError as exc:
            return self._error("command.spawn", str(exc), b"", str(exc).encode(), None)
        stdout = completed.stdout
        stderr = completed.stderr
        if len(stdout) + len(stderr) > spec.max_output_bytes:
            return self._error(
                "command.output_limit",
                "command verifier output exceeded the configured byte limit",
                stdout,
                stderr,
                completed.returncode,
            )
        stdout_artifact = self._artifact(stdout)
        stderr_artifact = self._artifact(stderr)
        artifacts = [item for item in (stdout_artifact, stderr_artifact) if item is not None]
        if completed.returncode == 0:
            result = VerifierResult(
                schema_version="1.0",
                status=VerifierStatus.PASSED,
                summary="command verifier passed",
                artifacts=artifacts,
            )
        else:
            result = VerifierResult(
                schema_version="1.0",
                status=VerifierStatus.FAILED,
                summary=f"command verifier exited with {completed.returncode}",
                failure_details=[f"exit code {completed.returncode}"],
                artifacts=artifacts,
            )
        return CommandVerifierOutcome(
            result, stdout_artifact, stderr_artifact, completed.returncode
        )

    def _error(
        self,
        code: str,
        message: str,
        stdout: bytes,
        stderr: bytes,
        exit_code: int | None,
    ) -> CommandVerifierOutcome:
        stdout_artifact = self._artifact(stdout)
        stderr_artifact = self._artifact(stderr)
        artifacts = [item for item in (stdout_artifact, stderr_artifact) if item is not None]
        error = Error(
            schema_version="1.0",
            kind=ErrorKind.INFRASTRUCTURE,
            code=code,
            message=message,
            retryable=code == "command.timeout",
            details={"exit_code": exit_code},
        )
        result = VerifierResult(
            schema_version="1.0",
            status=VerifierStatus.ERROR,
            summary=message,
            artifacts=artifacts,
            error=error,
        )
        return CommandVerifierOutcome(result, stdout_artifact, stderr_artifact, exit_code)

    def _artifact(self, content: bytes) -> Artifact | None:
        if not content:
            return None
        return self.artifact_store.put_bytes(
            content, media_type="text/plain", kind=ArtifactKind.TEST_RESULT
        )

    @staticmethod
    def _bytes(value: str | bytes | None) -> bytes:
        if value is None:
            return b""
        return value if isinstance(value, bytes) else value.encode("utf-8")
