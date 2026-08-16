"""Codex CLI boundary: help-derived capabilities, argv, JSONL, and process supervision."""

from __future__ import annotations

import json
import re
import subprocess
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import ClassVar, cast

from pydantic import ValidationError

from graph_engineering.executor import (
    ExecutorCapabilities,
    ExecutorEvent,
    ExecutorOutcome,
    ExecutorRequest,
    SessionHandle,
)
from graph_engineering.models import Error, ExecutorResult
from graph_engineering.models.common import ArtifactKind, ErrorKind
from graph_engineering.models.results import ExecutorStatus
from graph_engineering.review.models import ReviewResult, StructuredReviewOutcome
from graph_engineering.runtime.artifacts import ArtifactStore

CommandRun = Callable[[list[str]], subprocess.CompletedProcess[str]]
Invoke = Callable[[list[str], str, Path], tuple[int, str, str]]


class CodexPreflightError(RuntimeError):
    pass


class UnsupportedCodexCapability(CodexPreflightError):
    pass


def _run_text(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=30,
    )


class CodexPreflight:
    def __init__(self, *, executable: str = "codex", run: CommandRun = _run_text) -> None:
        self.executable = executable
        self._run = run

    def inspect(self) -> ExecutorCapabilities:
        try:
            version_result = self._run([self.executable, "--version"])
            login_result = self._run([self.executable, "login", "status"])
            root_help = self._run([self.executable, "--help"])
            exec_help = self._run([self.executable, "exec", "--help"])
            resume_help = self._run([self.executable, "exec", "resume", "--help"])
            review_help = self._run([self.executable, "exec", "review", "--help"])
        except (OSError, subprocess.SubprocessError) as exc:
            raise CodexPreflightError(f"Codex CLI preflight failed: {exc}") from exc
        match = re.search(r"(?:codex-cli\s+)?(\d+\.\d+\.\d+)", version_result.stdout or "")
        version = match.group(1) if match else "unknown"
        root = (root_help.stdout or "") + (root_help.stderr or "")
        execute = (exec_help.stdout or "") + (exec_help.stderr or "")
        resume = (resume_help.stdout or "") + (resume_help.stderr or "")
        review = (review_help.stdout or "") + (review_help.stderr or "")
        login = ((login_result.stdout or "") + (login_result.stderr or "")).lower()
        return ExecutorCapabilities(
            provider="codex",
            version=version,
            authenticated=login_result.returncode == 0 and "logged in" in login,
            json_events="--json" in execute,
            output_schema="--output-schema" in execute,
            output_last_message="--output-last-message" in execute,
            resume="resume" in resume and "--json" in resume and "--output-schema" in resume,
            review="review" in review and "--json" in review and "--output-schema" in review,
            workspace_write="--sandbox" in execute,
            read_only="--sandbox" in execute,
            approval_never="--ask-for-approval" in root and "never" in root,
        )


class CodexJsonlParser:
    _KNOWN: ClassVar[dict[str, str]] = {
        "thread.started": "session_started",
        "turn.started": "turn_started",
        "turn.completed": "turn_completed",
        "turn.failed": "turn_failed",
        "item.started": "item_started",
        "item.updated": "item_updated",
        "item.completed": "item_completed",
        "error": "error",
    }

    def parse_lines(self, lines: Iterable[str]) -> tuple[ExecutorEvent, ...]:
        events: list[ExecutorEvent] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                events.append(ExecutorEvent("unknown", None, None, {"raw_text": line}))
                continue
            if not isinstance(value, dict):
                events.append(ExecutorEvent("unknown", None, None, {"value": value}))
                continue
            data = cast(dict[str, object], value)
            provider_type = data.get("type")
            provider_event_type = provider_type if isinstance(provider_type, str) else None
            thread_id = data.get("thread_id") or data.get("session_id")
            session_id = thread_id if isinstance(thread_id, str) else None
            events.append(
                ExecutorEvent(
                    self._KNOWN.get(provider_event_type or "", "unknown"),
                    provider_event_type,
                    session_id,
                    data,
                )
            )
        return tuple(events)


class CodexAdapter:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        preflight: CodexPreflight | None = None,
        executable: str = "codex",
        invoke: Invoke | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.preflight = preflight or CodexPreflight(executable=executable)
        self.executable = executable
        self._invoke_override = invoke
        self._active: dict[str, subprocess.Popen[str]] = {}
        self._active_lock = threading.Lock()

    def capabilities(self) -> ExecutorCapabilities:
        return self.preflight.inspect()

    def start(self, request: ExecutorRequest) -> ExecutorOutcome:
        return self._execute("start", request, None)

    def resume(self, session: SessionHandle, request: ExecutorRequest) -> ExecutorOutcome:
        if session.provider != "codex":
            raise ValueError("cannot resume a non-Codex Session")
        return self._execute("resume", request, session)

    def review(self, request: ExecutorRequest) -> ExecutorOutcome:
        return self._execute("structured_review", request, None)

    def review_structured(self, request: ExecutorRequest) -> StructuredReviewOutcome:
        """Run Codex review and validate the final message as structured findings."""

        outcome = self._execute("structured_review", request, None)
        output_path = request.control_directory / f"{request.attempt_id}.last-message.json"
        result = ReviewResult.model_validate_json(output_path.read_text(encoding="utf-8"))
        return StructuredReviewOutcome(
            session=outcome.session,
            result=result,
            events=outcome.events,
            raw_stdout=outcome.raw_stdout,
            raw_stderr=outcome.raw_stderr,
            exit_code=outcome.exit_code,
        )

    def cancel(self, session: SessionHandle, *, grace_seconds: float = 5) -> bool:
        with self._active_lock:
            process = self._active.get(session.provider_session_id)
        if process is None or process.poll() is not None:
            return True
        process.terminate()
        try:
            process.wait(timeout=grace_seconds)
            return True
        except subprocess.TimeoutExpired:
            return False

    def is_active(self, session: SessionHandle) -> bool:
        with self._active_lock:
            process = self._active.get(session.provider_session_id)
        return process is not None and process.poll() is None

    def _execute(
        self, mode: str, request: ExecutorRequest, session: SessionHandle | None
    ) -> ExecutorOutcome:
        capabilities = self.capabilities()
        if not capabilities.supports_required_phase2:
            raise UnsupportedCodexCapability(
                f"Codex {capabilities.version} lacks required Phase 2 capabilities"
            )
        request.control_directory.mkdir(parents=True, exist_ok=True)
        schema_path = request.control_directory / f"{request.attempt_id}.output.schema.json"
        output_path = request.control_directory / f"{request.attempt_id}.last-message.json"
        schema_path.write_text(
            json.dumps(
                self._strict_output_schema(request.output_schema),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        argv = self._argv(mode, request, schema_path, output_path, session)
        prompt = f"{request.objective}\n\n{request.context}"
        if self._invoke_override is None:
            active_key = session.provider_session_id if session is not None else request.attempt_id
            exit_code, stdout, stderr = self._invoke(
                argv, prompt, output_path, request, active_key=active_key
            )
        else:
            exit_code, stdout, stderr = self._invoke_override(argv, prompt, output_path)
        stdout_artifact = self.artifact_store.put_bytes(
            stdout.encode("utf-8"), media_type="application/x-ndjson", kind=ArtifactKind.LOG
        )
        stderr_artifact = (
            self.artifact_store.put_bytes(
                stderr.encode("utf-8"), media_type="text/plain", kind=ArtifactKind.LOG
            )
            if stderr
            else None
        )
        events = CodexJsonlParser().parse_lines(stdout.splitlines())
        provider_session_id = next(
            (event.session_id for event in events if event.session_id is not None),
            session.provider_session_id
            if session is not None
            else f"unavailable:{request.attempt_id}",
        )
        handle = SessionHandle("codex", provider_session_id, capabilities.version)
        result = self._load_result(output_path, exit_code, stderr)
        return ExecutorOutcome(handle, result, events, stdout_artifact, stderr_artifact, exit_code)

    @classmethod
    def _strict_output_schema(cls, schema: dict[str, object]) -> dict[str, object]:
        """Adapt ordinary JSON Schema to Codex Structured Outputs strict-object rules."""

        def visit(value: object) -> object:
            if isinstance(value, list):
                return [visit(item) for item in value]
            if not isinstance(value, dict):
                return value
            result = {
                str(key): visit(item)
                for key, item in value.items()
                if key not in {"default", "examples"}
            }
            properties = result.get("properties")
            if isinstance(properties, dict):
                result["required"] = list(properties)
                result["additionalProperties"] = False
            elif result.get("type") == "object":
                result["properties"] = {}
                result["required"] = []
                result["additionalProperties"] = False
            return result

        return cast(dict[str, object], visit(schema))

    def _argv(
        self,
        mode: str,
        request: ExecutorRequest,
        schema_path: Path,
        output_path: Path,
        session: SessionHandle | None,
    ) -> list[str]:
        argv = [self.executable, "--ask-for-approval", "never", "exec"]
        if mode == "resume":
            if session is None:
                raise ValueError("resume requires a Session")
            argv.extend(["resume", session.provider_session_id])
        else:
            argv.extend(["--sandbox", request.sandbox.value])
            if mode == "native_review":
                argv.append("review")
        argv.extend(
            [
                "--json",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
        )
        return argv

    def _invoke(
        self,
        argv: list[str],
        prompt: str,
        output: Path,
        request: ExecutorRequest,
        *,
        active_key: str,
    ) -> tuple[int, str, str]:
        process = subprocess.Popen(
            argv,
            cwd=request.working_directory,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        with self._active_lock:
            self._active[active_key] = process
        try:
            stdout, stderr = process.communicate(prompt, timeout=request.timeout_seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            stdout, stderr = process.communicate()
            stderr = f"{stderr}\nCodex process timed out"
            return 124, stdout, stderr
        finally:
            with self._active_lock:
                self._active.pop(active_key, None)
        return int(process.returncode or 0), stdout, stderr

    @staticmethod
    def _load_result(output: Path, exit_code: int, stderr: str) -> ExecutorResult:
        try:
            return ExecutorResult.model_validate_json(output.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            error = Error(
                schema_version="1.0",
                kind=ErrorKind.EXECUTOR,
                code="codex.structured_output_invalid",
                message=f"Codex structured output was invalid: {exc}",
                retryable=False,
                details={"exit_code": exit_code, "stderr_present": bool(stderr)},
            )
            return ExecutorResult(
                schema_version="1.0",
                status=ExecutorStatus.ERROR,
                summary=error.message,
                error=error,
            )
