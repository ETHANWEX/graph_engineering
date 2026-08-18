"""Argv-only project Verifier with a bounded JSON stdin/stdout protocol."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping

from graph_engineering.models import Artifact, Error, VerifierResult
from graph_engineering.models.common import ArtifactKind, ErrorKind
from graph_engineering.models.results import VerifierStatus
from graph_engineering.runtime.artifacts import ArtifactStore

from .policy import CapabilityPolicy, SecretRedactor, SecretResolver
from .types import VerifierManifest, VerifierOutcome, VerifierRequest


class SubprocessVerifier:
    def __init__(
        self,
        manifest: VerifierManifest,
        artifacts: ArtifactStore,
        *,
        secrets: Mapping[str, str] | None = None,
        timeout_seconds: float = 300,
        max_output_bytes: int = 1024 * 1024,
        can_start: Callable[[], bool] | None = None,
    ) -> None:
        if manifest.verifier_type != "project/subprocess":
            raise ValueError("SubprocessVerifier requires a project/subprocess Manifest")
        if timeout_seconds <= 0 or max_output_bytes <= 0:
            raise ValueError("subprocess limits must be positive")
        self.manifest = manifest
        self.artifacts = artifacts
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self._secrets = SecretResolver(secrets or {}).resolve(manifest)
        self._redactor = SecretRedactor(self._secrets)
        self._can_start = can_start or (lambda: True)
        self._active: subprocess.Popen[bytes] | None = None

    def execute(self, request: VerifierRequest) -> VerifierOutcome:
        if not self._can_start():
            return self._error("subprocess.barrier", "persisted Run barrier forbids subprocess")
        try:
            CapabilityPolicy.require_path(
                self.manifest,
                request.working_directory,
                writable=False,
                roots=(request.working_directory, request.artifact_directory),
            )
        except Exception as exc:
            return self._error("subprocess.filesystem", str(exc))
        stdin = json.dumps(
            {
                "schema_version": "1.0",
                "run_id": request.run_id,
                "node_id": request.node_id,
                "attempt_id": request.attempt_id,
                "payload": request.payload or {},
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TMP", "TEMP"}
        }
        environment.update(self._secrets)
        try:
            process = subprocess.Popen(
                list(self.manifest.entrypoint),
                cwd=request.working_directory,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                shell=False,
            )
            self._active = process
            stdout, stderr = process.communicate(stdin, timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            stdout, stderr = process.communicate()
            return self._error_with_artifacts(
                "subprocess.timeout", "project Verifier timed out", stdout, stderr, retryable=True
            )
        except OSError as exc:
            return self._error("subprocess.spawn", self._redactor.redact(str(exc)))
        finally:
            self._active = None
        redacted_stdout = self._redactor.redact_bytes(stdout)
        redacted_stderr = self._redactor.redact_bytes(stderr)
        if len(stdout) + len(stderr) > self.max_output_bytes:
            return self._error_with_artifacts(
                "subprocess.output_limit",
                "project Verifier output exceeded configured byte limit",
                redacted_stdout,
                redacted_stderr,
            )
        if process.returncode != 0:
            return self._error_with_artifacts(
                "subprocess.exit",
                f"project Verifier exited abnormally with {process.returncode}",
                redacted_stdout,
                redacted_stderr,
            )
        stdout_artifact = self._artifact(redacted_stdout, "application/json")
        stderr_artifact = self._artifact(redacted_stderr, "text/plain")
        artifacts = tuple(item for item in (stdout_artifact, stderr_artifact) if item is not None)
        try:
            result = VerifierResult.model_validate_json(redacted_stdout)
        except Exception as exc:
            return self._error_with_artifacts(
                "subprocess.protocol",
                self._redactor.redact(f"invalid structured Verifier output: {exc}"),
                redacted_stdout,
                redacted_stderr,
            )
        result = result.model_copy(update={"artifacts": [*result.artifacts, *artifacts]})
        return VerifierOutcome(result=result, artifacts=artifacts, exit_code=process.returncode)

    def poll(self, handle: str) -> VerifierOutcome:
        return self._error(
            "subprocess.handle", "project subprocess does not expose external handles"
        )

    def cancel(self, handle: str) -> VerifierOutcome:
        process = self._active
        if process is None or process.poll() is not None:
            return VerifierOutcome(
                VerifierResult(
                    schema_version="1.0",
                    status=VerifierStatus.CANCELLED,
                    summary="project Verifier is no longer running",
                )
            )
        process.terminate()
        return VerifierOutcome(
            VerifierResult(
                schema_version="1.0",
                status=VerifierStatus.CANCELLED,
                summary="project Verifier cancellation requested",
            )
        )

    def _error_with_artifacts(
        self,
        code: str,
        message: str,
        stdout: bytes,
        stderr: bytes,
        *,
        retryable: bool = False,
    ) -> VerifierOutcome:
        stdout_artifact = self._artifact(self._redactor.redact_bytes(stdout), "application/json")
        stderr_artifact = self._artifact(self._redactor.redact_bytes(stderr), "text/plain")
        artifacts = tuple(item for item in (stdout_artifact, stderr_artifact) if item is not None)
        outcome = self._error(code, message, retryable=retryable)
        result = outcome.result.model_copy(update={"artifacts": list(artifacts)})
        return VerifierOutcome(result, artifacts)

    def _artifact(self, content: bytes, media_type: str) -> Artifact | None:
        if not content:
            return None
        return self.artifacts.put_bytes(
            content, media_type=media_type, kind=ArtifactKind.TEST_RESULT
        )

    @staticmethod
    def _error(code: str, message: str, *, retryable: bool = False) -> VerifierOutcome:
        error = Error(
            schema_version="1.0",
            kind=ErrorKind.INFRASTRUCTURE,
            code=code,
            message=message,
            retryable=retryable,
        )
        return VerifierOutcome(
            VerifierResult(
                schema_version="1.0",
                status=VerifierStatus.ERROR,
                summary=message,
                retryable=retryable,
                error=error,
            )
        )
