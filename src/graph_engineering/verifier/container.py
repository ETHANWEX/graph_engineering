"""Fail-closed container Verifier provider and Docker-compatible adapter boundary."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Literal, Protocol, cast

from graph_engineering.models import Artifact, Error, VerifierResult
from graph_engineering.models.common import ArtifactKind, ErrorKind
from graph_engineering.models.results import VerifierStatus
from graph_engineering.observability import (
    NoOpTelemetryProvider,
    TelemetryIdentity,
    TelemetryProvider,
)
from graph_engineering.runtime.artifacts import ArtifactStore
from graph_engineering.runtime.store import StateStore, timestamp

from .policy import CapabilityViolation, SecretRedactor, SecretResolver
from .types import (
    ContainerImageAllowlist,
    ContainerMount,
    ContainerNetworkPolicy,
    ContainerResourceLimits,
    VerifierManifest,
    VerifierOutcome,
    VerifierRequest,
)


class ContainerPreflightKind(StrEnum):
    RUNTIME_MISSING = "runtime_missing"
    VERSION_INCOMPATIBLE = "version_incompatible"
    DAEMON_UNAVAILABLE = "daemon_unavailable"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"


class ContainerPreflightError(RuntimeError):
    def __init__(self, kind: ContainerPreflightKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class ContainerStartUncertainError(RuntimeError):
    """The runtime may have created a container but returned no durable handle."""


@dataclass(frozen=True)
class ContainerAdapterCapabilities:
    streaming_output: bool = False
    exact_network_policy: bool = False


@dataclass(frozen=True)
class ContainerRuntimeInfo:
    runtime: str
    version: str
    daemon_available: bool
    capabilities: ContainerAdapterCapabilities


@dataclass(frozen=True)
class ResolvedContainerMount:
    source: Path
    target: str
    writable: bool
    classification: str


@dataclass(frozen=True)
class ContainerStartRequest:
    owner_id: str
    image_reference: str
    platform: str
    entrypoint: tuple[str, ...]
    config: Mapping[str, str | int | float | bool]
    resources: ContainerResourceLimits
    mounts: tuple[ResolvedContainerMount, ...]
    network: ContainerNetworkPolicy
    secret_environment: Mapping[str, str]


@dataclass(frozen=True)
class ContainerStartResult:
    handle: str

    def __post_init__(self) -> None:
        if not self.handle:
            raise ValueError("container runtime handle must not be empty")


@dataclass(frozen=True)
class ContainerArtifact:
    name: str
    content: bytes
    media_type: str = "application/octet-stream"


@dataclass(frozen=True)
class ContainerInspection:
    state: Literal["running", "succeeded", "failed", "cancelled", "error"]
    exit_code: int | None = None
    stdout_chunks: tuple[bytes, ...] = ()
    stderr_chunks: tuple[bytes, ...] = ()
    artifacts: tuple[ContainerArtifact, ...] = ()
    error_message: str | None = None


@dataclass(frozen=True)
class ContainerStopResult:
    settled: bool
    residual_effect: str | None = None


@dataclass(frozen=True)
class ContainerCleanupResult:
    success: bool
    residual_effect: str | None = None


class ContainerRuntimeAdapter(Protocol):
    def preflight(self) -> ContainerRuntimeInfo: ...

    def start(self, request: ContainerStartRequest) -> ContainerStartResult: ...

    def inspect(self, handle: str) -> ContainerInspection: ...

    def stop(self, handle: str, timeout_seconds: float) -> ContainerStopResult: ...

    def cleanup(self, owner_id: str) -> ContainerCleanupResult: ...


class DockerCLIAdapter:
    """Minimal Docker-compatible CLI adapter; it never installs or starts the runtime."""

    def __init__(self, executable: str = "docker", *, minimum_major: int = 24) -> None:
        self.executable = executable
        self.minimum_major = minimum_major
        self._owners: dict[str, str] = {}
        self._secret_files: dict[str, Path] = {}
        self._log_limits: dict[str, tuple[int, int]] = {}

    def preflight(self) -> ContainerRuntimeInfo:
        executable = shutil.which(self.executable)
        if executable is None:
            raise ContainerPreflightError(
                ContainerPreflightKind.RUNTIME_MISSING,
                f"container runtime executable is unavailable: {self.executable}",
            )
        try:
            completed = subprocess.run(
                [executable, "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                check=False,
                timeout=10,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ContainerPreflightError(
                ContainerPreflightKind.DAEMON_UNAVAILABLE, "container daemon is unavailable"
            ) from exc
        version = completed.stdout.decode("utf-8", errors="replace").strip()
        if completed.returncode != 0 or not version:
            raise ContainerPreflightError(
                ContainerPreflightKind.DAEMON_UNAVAILABLE, "container daemon is unavailable"
            )
        try:
            major = int(version.split(".", 1)[0])
        except ValueError as exc:
            raise ContainerPreflightError(
                ContainerPreflightKind.VERSION_INCOMPATIBLE,
                f"unrecognized container runtime version: {version}",
            ) from exc
        if major < self.minimum_major:
            raise ContainerPreflightError(
                ContainerPreflightKind.VERSION_INCOMPATIBLE,
                f"container runtime {version} is older than required {self.minimum_major}",
            )
        return ContainerRuntimeInfo(
            runtime=self.executable,
            version=version,
            daemon_available=True,
            capabilities=ContainerAdapterCapabilities(streaming_output=True),
        )

    def start(self, request: ContainerStartRequest) -> ContainerStartResult:
        if getattr(request.network, "enabled", False):
            raise ContainerPreflightError(
                ContainerPreflightKind.CAPABILITY_UNAVAILABLE,
                "Docker CLI adapter cannot enforce exact DNS/redirect/proxy network policy",
            )
        executable = shutil.which(self.executable)
        if executable is None:
            raise ContainerPreflightError(
                ContainerPreflightKind.RUNTIME_MISSING, "container runtime disappeared"
            )
        name = self._owner_name(request.owner_id)
        argv = [
            executable,
            "create",
            "--name",
            name,
            "--label",
            f"graph-engineering.owner={request.owner_id}",
            "--network",
            "none",
            "--read-only",
            "--cpus",
            str(request.resources.cpu_count),
            "--memory",
            str(request.resources.memory_bytes),
            "--pids-limit",
            str(request.resources.pids),
            "--platform",
            request.platform,
        ]
        for mount in request.mounts:
            mode = "rw" if mount.writable else "ro"
            argv.extend(["--mount", f"type=bind,src={mount.source},dst={mount.target},{mode}"])
        if request.secret_environment:
            descriptor, secret_name = tempfile.mkstemp(prefix="ge-container-secret-", suffix=".env")
            secret_path = Path(secret_name)
            try:
                os.chmod(secret_path, stat.S_IRUSR | stat.S_IWUSR)
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                    for name, value in sorted(request.secret_environment.items()):
                        stream.write(f"{name}={value}\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                with suppress(OSError):
                    os.close(descriptor)
                secret_path.unlink(missing_ok=True)
                raise
            self._secret_files[request.owner_id] = secret_path
            argv.extend(["--env-file", str(secret_path)])
        argv.extend([request.image_reference, *request.entrypoint])
        completed = subprocess.run(argv, capture_output=True, check=False, timeout=30, shell=False)
        handle = completed.stdout.decode("utf-8", errors="replace").strip()
        if completed.returncode != 0:
            self._remove_secret_file(request.owner_id)
            raise RuntimeError("container creation failed")
        if not handle:
            raise ContainerStartUncertainError("container create returned no handle")
        self._owners[request.owner_id] = handle
        subprocess.run(
            [executable, "start", handle], capture_output=True, check=False, timeout=30, shell=False
        )
        self._log_limits[handle] = (
            request.resources.max_stdout_bytes,
            request.resources.max_stderr_bytes,
        )
        return ContainerStartResult(handle)

    def inspect(self, handle: str) -> ContainerInspection:
        executable = shutil.which(self.executable)
        if executable is None:
            raise ContainerPreflightError(
                ContainerPreflightKind.RUNTIME_MISSING, "container runtime disappeared"
            )
        completed = subprocess.run(
            [executable, "inspect", "--format", "{{.State.Status}} {{.State.ExitCode}}", handle],
            capture_output=True,
            check=False,
            timeout=10,
            shell=False,
        )
        if completed.returncode != 0:
            return ContainerInspection(state="error", error_message="container inspect failed")
        fields = completed.stdout.decode("utf-8", errors="replace").strip().split()
        if not fields or fields[0] in {"created", "running", "restarting", "paused"}:
            return ContainerInspection(state="running")
        exit_code = int(fields[1]) if len(fields) > 1 and fields[1].lstrip("-").isdigit() else None
        stdout_limit, stderr_limit = self._log_limits.get(handle, (1024 * 1024, 1024 * 1024))
        stdout, stderr = self._bounded_logs(
            [executable, "logs", handle], stdout_limit, stderr_limit
        )
        state: Literal["succeeded", "failed", "cancelled", "error"]
        state = "succeeded" if exit_code == 0 else "failed"
        return ContainerInspection(
            state=state,
            exit_code=exit_code,
            stdout_chunks=(stdout,),
            stderr_chunks=(stderr,),
        )

    def stop(self, handle: str, timeout_seconds: float) -> ContainerStopResult:
        executable = shutil.which(self.executable)
        if executable is None:
            return ContainerStopResult(False, "container runtime disappeared during stop")
        completed = subprocess.run(
            [executable, "stop", "--time", str(max(1, int(timeout_seconds))), handle],
            capture_output=True,
            check=False,
            timeout=timeout_seconds + 5,
            shell=False,
        )
        return ContainerStopResult(
            completed.returncode == 0,
            None if completed.returncode == 0 else "container stop did not settle",
        )

    def cleanup(self, owner_id: str) -> ContainerCleanupResult:
        handle = self._owners.get(owner_id, self._owner_name(owner_id))
        executable = shutil.which(self.executable)
        if executable is None:
            return ContainerCleanupResult(False, "container runtime disappeared during cleanup")
        inspected = subprocess.run(
            [
                executable,
                "inspect",
                "--format",
                '{{index .Config.Labels "graph-engineering.owner"}}',
                handle,
            ],
            capture_output=True,
            check=False,
            timeout=10,
            shell=False,
        )
        if inspected.returncode != 0:
            self._remove_secret_file(owner_id)
            return ContainerCleanupResult(True)
        if inspected.stdout.decode("utf-8", errors="replace").strip() != owner_id:
            return ContainerCleanupResult(False, "container ownership could not be verified")
        removed = subprocess.run(
            [executable, "rm", "-f", handle],
            capture_output=True,
            check=False,
            timeout=20,
            shell=False,
        )
        if removed.returncode == 0:
            self._owners.pop(owner_id, None)
            self._log_limits.pop(handle, None)
            self._remove_secret_file(owner_id)
            return ContainerCleanupResult(True)
        return ContainerCleanupResult(False, "owned container cleanup failed")

    def _remove_secret_file(self, owner_id: str) -> None:
        secret_path = self._secret_files.pop(owner_id, None)
        if secret_path is not None:
            secret_path.unlink(missing_ok=True)

    @staticmethod
    def _owner_name(owner_id: str) -> str:
        return "ge-" + owner_id.replace(":", "-")[-48:]

    @staticmethod
    def _bounded_logs(argv: list[str], stdout_limit: int, stderr_limit: int) -> tuple[bytes, bytes]:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        assert process.stdout is not None and process.stderr is not None
        outputs = [bytearray(), bytearray()]

        def read_bounded(stream: BinaryIO, target: bytearray, limit: int) -> None:
            while len(target) <= limit:
                chunk = stream.read(min(64 * 1024, limit + 1 - len(target)))
                if not chunk:
                    break
                target.extend(chunk)
                if len(target) > limit:
                    with suppress(OSError):
                        process.terminate()
                    break

        readers = (
            threading.Thread(target=read_bounded, args=(process.stdout, outputs[0], stdout_limit)),
            threading.Thread(target=read_bounded, args=(process.stderr, outputs[1], stderr_limit)),
        )
        for reader in readers:
            reader.start()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=5)
        return bytes(outputs[0]), bytes(outputs[1])


class ContainerVerifier:
    def __init__(
        self,
        manifest: VerifierManifest,
        artifacts: ArtifactStore,
        state: StateStore,
        adapter: ContainerRuntimeAdapter,
        *,
        image_allowlist: ContainerImageAllowlist,
        authorized_roots: tuple[Path, ...],
        secrets: Mapping[str, str] | None = None,
        can_start: Callable[[], bool] | None = None,
        telemetry: TelemetryProvider | None = None,
    ) -> None:
        if manifest.verifier_type != "project/container" or manifest.container is None:
            raise ValueError("ContainerVerifier requires a project/container Manifest")
        self.manifest = manifest
        self.spec = manifest.container
        self.artifacts = artifacts
        self.state = state
        self.state.migrate()
        self.adapter = adapter
        self.image_allowlist = image_allowlist
        self.authorized_roots = tuple(root.resolve() for root in authorized_roots)
        self._secrets = SecretResolver(secrets or {}).resolve(manifest)
        self._redactor = SecretRedactor(self._secrets)
        self._can_start = can_start or (lambda: True)
        self.telemetry = telemetry or NoOpTelemetryProvider()
        self._frozen_fingerprint = self.spec.fingerprint()
        self._slots = threading.BoundedSemaphore(self.spec.resources.max_concurrency)
        self._active_handles: set[str] = set()
        self._lock = threading.Lock()

    def execute(self, request: VerifierRequest) -> VerifierOutcome:
        if not request.idempotency_key:
            return self._error(
                "container.idempotency", "container execution requires an idempotency key"
            )
        existing = self._by_key(request.idempotency_key)
        if existing is not None:
            if existing["result_json"]:
                return VerifierOutcome(
                    VerifierResult.model_validate_json(str(existing["result_json"]))
                )
            if existing["handle"]:
                return self.poll(str(existing["handle"]))
            return self._error(
                "container.start_uncertain",
                "container start intent has no checkpointed handle; refusing retrigger",
            )
        preflight = self._validate_before_effect(request)
        if preflight is not None:
            return preflight
        with self.state.read_connection() as connection:
            active_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM container_executions "
                    "WHERE state IN ('starting','running','uncertain')"
                ).fetchone()[0]
            )
        if active_count >= self.spec.resources.max_concurrency:
            return self._error("container.concurrency", "container concurrency limit is exhausted")
        if not self._slots.acquire(blocking=False):
            return self._error("container.concurrency", "container concurrency limit is exhausted")
        owner_id = f"container:{request.run_id}:{request.node_id}:{request.attempt_id}"
        try:
            with self.state.transaction() as connection:
                run = connection.execute(
                    "SELECT status,barrier FROM runs WHERE run_id=?", (request.run_id,)
                ).fetchone()
                if run is not None and (
                    str(run["status"]) != "running" or run["barrier"] is not None
                ):
                    raise CapabilityViolation("persisted Run barrier forbids a new container")
                if not self._can_start():
                    raise CapabilityViolation("persisted Run barrier forbids a new container")
                execution_id = f"container-execution:{uuid.uuid4()}"
                connection.execute(
                    "INSERT INTO container_executions(execution_id,run_id,node_id,attempt_id,"
                    "idempotency_key,owner_id,state,image_digest,config_fingerprint,stdout_bytes,"
                    "stderr_bytes,artifact_bytes,cleanup_state,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,'starting',?,?,0,0,0,'pending',?,?)",
                    (
                        execution_id,
                        request.run_id,
                        request.node_id,
                        request.attempt_id,
                        request.idempotency_key,
                        owner_id,
                        self.spec.image.digest,
                        self.spec.fingerprint(),
                        timestamp(),
                        timestamp(),
                    ),
                )
                self.state.enqueue_event(
                    connection,
                    "verifier.container.starting",
                    request.run_id,
                    node_id=request.node_id,
                    attempt_id=request.attempt_id,
                    payload={"owner_id": owner_id, "image_digest": self.spec.image.digest},
                )
            if not self._can_start():
                self._mark_without_start(request.idempotency_key, "barrier")
                self._slots.release()
                return self._error(
                    "container.barrier", "persisted Run barrier forbids a new container"
                )
            resolved = self._resolve_mounts(request)
            secret_environment = {
                name: self._secrets[reference]
                for name, reference in self.spec.secret_environment.items()
            }
            start_request = ContainerStartRequest(
                owner_id=owner_id,
                image_reference=self.spec.image.reference,
                platform=self.spec.image.platform,
                entrypoint=self.spec.entrypoint,
                config=self.spec.config,
                resources=self.spec.resources,
                mounts=resolved,
                network=self.spec.network,
                secret_environment=secret_environment,
            )
            started = self.adapter.start(start_request)
            with self.state.transaction() as connection:
                connection.execute(
                    "UPDATE container_executions SET state='running',handle=?,started_at=?,"
                    "deadline_at=?,updated_at=? WHERE idempotency_key=?",
                    (
                        started.handle,
                        timestamp(),
                        (datetime.now(UTC) + timedelta(seconds=self.spec.resources.timeout_seconds))
                        .isoformat()
                        .replace("+00:00", "Z"),
                        timestamp(),
                        request.idempotency_key,
                    ),
                )
                self.state.enqueue_event(
                    connection,
                    "verifier.container.handle_checkpointed",
                    request.run_id,
                    node_id=request.node_id,
                    attempt_id=request.attempt_id,
                    payload={"handle": started.handle, "owner_id": owner_id},
                )
            with self._lock:
                self._active_handles.add(started.handle)
            return VerifierOutcome(
                VerifierResult(
                    schema_version="1.0",
                    status=VerifierStatus.PENDING,
                    summary="container Verifier started and handle checkpointed",
                    external_handle=started.handle,
                    retryable=True,
                )
            )
        except ContainerStartUncertainError as exc:
            self._slots.release()
            try:
                cleanup = self.adapter.cleanup(owner_id)
            except Exception as cleanup_error:
                cleanup = ContainerCleanupResult(False, self._redactor.redact(str(cleanup_error)))
            return self._persist_uncertain(request.idempotency_key, str(exc), cleanup)
        except ContainerPreflightError as exc:
            self._slots.release()
            return self._error(f"container.preflight.{exc.kind.value}", str(exc))
        except CapabilityViolation as exc:
            self._slots.release()
            return self._error("container.barrier", str(exc), kind=ErrorKind.POLICY)
        except Exception as exc:
            self._slots.release()
            return self._persist_error(
                request.idempotency_key,
                "container.start",
                self._redactor.redact(str(exc)) or "container start failed",
            )

    def poll(self, handle: str) -> VerifierOutcome:
        row = self._by_handle(handle)
        if row is None:
            return self._error("container.handle", "container handle is not owned by this provider")
        if row["result_json"]:
            return VerifierOutcome(VerifierResult.model_validate_json(str(row["result_json"])))
        if row["deadline_at"] and datetime.now(UTC) >= datetime.fromisoformat(
            str(row["deadline_at"]).replace("Z", "+00:00")
        ):
            self.adapter.stop(handle, min(10.0, self.spec.resources.timeout_seconds))
            return self._terminal_error(row, "container.timeout", "container wall-clock timeout")
        try:
            inspection = self.adapter.inspect(handle)
        except Exception as exc:
            return self._terminal_error(
                row,
                "container.inspect",
                self._redactor.redact(str(exc)) or "container inspect failed",
            )
        stdout_bytes = int(row["stdout_bytes"]) + sum(map(len, inspection.stdout_chunks))
        stderr_bytes = int(row["stderr_bytes"]) + sum(map(len, inspection.stderr_chunks))
        artifact_bytes = int(row["artifact_bytes"]) + sum(
            len(item.content) for item in inspection.artifacts
        )
        if (
            stdout_bytes > self.spec.resources.max_stdout_bytes
            or stderr_bytes > self.spec.resources.max_stderr_bytes
            or artifact_bytes > self.spec.resources.max_artifact_bytes
        ):
            self.adapter.stop(handle, min(10.0, self.spec.resources.timeout_seconds))
            return self._terminal_error(
                row, "container.output_limit", "container output or Artifact limit exceeded"
            )
        with self.state.transaction() as connection:
            connection.execute(
                "UPDATE container_executions SET stdout_bytes=?,stderr_bytes=?,artifact_bytes=?,"
                "updated_at=? WHERE handle=?",
                (stdout_bytes, stderr_bytes, artifact_bytes, timestamp(), handle),
            )
        if inspection.state == "running":
            return VerifierOutcome(
                VerifierResult(
                    schema_version="1.0",
                    status=VerifierStatus.PENDING,
                    summary="container Verifier remains active",
                    external_handle=handle,
                    retryable=True,
                )
            )
        artifacts = self._persist_artifacts(inspection)
        if inspection.state == "succeeded":
            result = VerifierResult(
                schema_version="1.0",
                status=VerifierStatus.PASSED,
                summary="container Verifier passed",
                artifacts=list(artifacts),
                metrics={"exit_code": inspection.exit_code},
            )
        elif inspection.state == "failed":
            result = VerifierResult(
                schema_version="1.0",
                status=VerifierStatus.FAILED,
                summary="container Verifier failed",
                failure_details=[f"container exit code {inspection.exit_code}"],
                artifacts=list(artifacts),
                metrics={"exit_code": inspection.exit_code},
            )
        elif inspection.state == "cancelled":
            result = VerifierResult(
                schema_version="1.0",
                status=VerifierStatus.CANCELLED,
                summary="container Verifier was cancelled",
                artifacts=list(artifacts),
            )
        else:
            result = self._error_result(
                "container.infrastructure",
                self._redactor.redact(inspection.error_message or "container infrastructure error"),
                artifacts=artifacts,
            )
        return self._finish(row, result)

    def cancel(self, handle: str) -> VerifierOutcome:
        row = self._by_handle(handle)
        if row is None:
            return self._error("container.handle", "container handle is not owned by this provider")
        if row["result_json"]:
            return VerifierOutcome(VerifierResult.model_validate_json(str(row["result_json"])))
        try:
            stopped = self.adapter.stop(handle, min(10.0, self.spec.resources.timeout_seconds))
        except Exception as exc:
            stopped = ContainerStopResult(False, self._redactor.redact(str(exc)))
        if not stopped.settled:
            cleanup = self.adapter.cleanup(str(row["owner_id"]))
            residual = (
                stopped.residual_effect or cleanup.residual_effect or "container state unknown"
            )
            return self._finish(
                row,
                self._error_result(
                    "container.residual_effect",
                    self._redactor.redact(residual),
                    details={"cleanup_success": cleanup.success},
                ),
                cleanup=cleanup,
            )
        result = VerifierResult(
            schema_version="1.0",
            status=VerifierStatus.CANCELLED,
            summary="container Verifier cancellation settled",
        )
        return self._finish(row, result)

    def _validate_before_effect(self, request: VerifierRequest) -> VerifierOutcome | None:
        if not self._can_start():
            return self._error(
                "container.barrier",
                "persisted Run barrier forbids a new container",
                kind=ErrorKind.POLICY,
            )
        if self.spec.fingerprint() != self._frozen_fingerprint:
            return self._error(
                "container.config_drift",
                "frozen container image or config drift detected",
                kind=ErrorKind.POLICY,
            )
        try:
            self.image_allowlist.require(self.spec.image)
            self._ensure_no_secret_identity_leak()
            self._resolve_mounts(request)
            info = self.adapter.preflight()
            if not info.daemon_available:
                raise ContainerPreflightError(
                    ContainerPreflightKind.DAEMON_UNAVAILABLE, "container daemon is unavailable"
                )
            if not info.capabilities.streaming_output:
                raise ContainerPreflightError(
                    ContainerPreflightKind.CAPABILITY_UNAVAILABLE,
                    "container runtime cannot enforce streaming output limits",
                )
            if self.spec.network.enabled and not info.capabilities.exact_network_policy:
                return self._error(
                    "container.network_policy",
                    "container runtime cannot reliably enforce exact network policy",
                    kind=ErrorKind.POLICY,
                )
        except ContainerPreflightError as exc:
            return self._error(f"container.preflight.{exc.kind.value}", str(exc))
        except CapabilityViolation as exc:
            code = "container.mount_policy" if "mount" in str(exc) else "container.image_policy"
            return self._error(code, str(exc), kind=ErrorKind.POLICY)
        except (OSError, ValueError) as exc:
            return self._error("container.mount_policy", str(exc), kind=ErrorKind.POLICY)
        return None

    def _resolve_mounts(self, request: VerifierRequest) -> tuple[ResolvedContainerMount, ...]:
        roots = tuple(
            dict.fromkeys(
                (
                    *self.authorized_roots,
                    request.working_directory.resolve(),
                    request.artifact_directory.resolve(),
                )
            )
        )
        resolved: list[ResolvedContainerMount] = []
        for mount in self.spec.mounts:
            self._validate_mount_target(mount)
            candidate: Path | None = None
            for root in roots:
                proposed = root / Path(mount.source)
                if proposed.exists():
                    candidate = self._safe_resolve(root, proposed)
                    break
            if candidate is None:
                raise CapabilityViolation(f"container mount source does not exist: {mount.source}")
            resolved.append(
                ResolvedContainerMount(
                    candidate, mount.target, mount.writable, mount.classification
                )
            )
        return tuple(resolved)

    @staticmethod
    def _safe_resolve(root: Path, candidate: Path) -> Path:
        root = root.resolve(strict=True)
        current = root
        relative = candidate.relative_to(root)
        for part in relative.parts:
            current = current / part
            info = current.lstat()
            attributes = getattr(info, "st_file_attributes", 0)
            reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            if current.is_symlink() or attributes & reparse:
                raise CapabilityViolation(
                    "container mount symlink/junction/reparse escape is forbidden"
                )
        resolved = candidate.resolve(strict=True)
        if resolved != root and root not in resolved.parents:
            raise CapabilityViolation("container mount escapes its authorized root")
        return resolved

    @staticmethod
    def _validate_mount_target(mount: ContainerMount) -> None:
        target = PurePosixPath(mount.target)
        blocked_exact = {"/var/run/docker.sock", "/run/docker.sock", "/etc", "/root", "/home"}
        blocked_prefixes = ("/etc/", "/root/", "/home/", "/proc/", "/sys/", "/dev/")
        text = target.as_posix()
        if text in blocked_exact or text.startswith(blocked_prefixes):
            raise CapabilityViolation("container mount target is a Docker socket or system path")

    def _ensure_no_secret_identity_leak(self) -> None:
        identity = json.dumps(
            {
                "image": self.spec.image.reference,
                "entrypoint": self.spec.entrypoint,
                "config": self.spec.config,
            },
            sort_keys=True,
        )
        if self._redactor.redact(identity) != identity:
            raise CapabilityViolation(
                "secret value must not appear in container identity or command"
            )

    def _persist_artifacts(self, inspection: ContainerInspection) -> tuple[Artifact, ...]:
        artifacts: list[Artifact] = []
        streams = (
            (inspection.stdout_chunks, "text/plain"),
            (inspection.stderr_chunks, "text/plain"),
        )
        for chunks, media_type in streams:
            redactor = self._redactor.stream()
            for chunk in chunks:
                redactor.feed(chunk.decode("utf-8", errors="replace"))
            content = redactor.feed("", final=True).encode("utf-8")
            if content:
                artifacts.append(
                    self.artifacts.put_bytes(
                        content, media_type=media_type, kind=ArtifactKind.TEST_RESULT
                    )
                )
        for item in inspection.artifacts:
            artifacts.append(
                self.artifacts.put_bytes(
                    self._redactor.redact_bytes(item.content),
                    media_type=item.media_type,
                    kind=ArtifactKind.TEST_RESULT,
                )
            )
        return tuple(artifacts)

    def _finish(
        self,
        row: sqlite3.Row,
        result: VerifierResult,
        *,
        cleanup: ContainerCleanupResult | None = None,
    ) -> VerifierOutcome:
        with self.telemetry.span(
            "ge.runtime.cleanup",
            TelemetryIdentity(
                run_id=str(row["run_id"]),
                node_id=str(row["node_id"]),
                attempt_id=str(row["attempt_id"]),
                external_effect_id=str(row["idempotency_key"]),
                provider_handle=str(row["handle"]) if row["handle"] else None,
            ),
            {"ge.component": "verifier", "ge.operation": "cleanup"},
        ) as span:
            outcome = self._finish_uninstrumented(row, result, cleanup=cleanup)
            span.set_result(outcome.result.status.value)
            return outcome

    def _finish_uninstrumented(
        self,
        row: sqlite3.Row,
        result: VerifierResult,
        *,
        cleanup: ContainerCleanupResult | None = None,
    ) -> VerifierOutcome:
        if cleanup is None:
            try:
                cleanup = self.adapter.cleanup(str(row["owner_id"]))
            except Exception as exc:
                cleanup = ContainerCleanupResult(False, self._redactor.redact(str(exc)))
        if not cleanup.success:
            cleanup_message = self._redactor.redact(
                cleanup.residual_effect or "owned container cleanup failed"
            )
            cleanup_artifact = self.artifacts.put_bytes(
                cleanup_message.encode("utf-8"),
                media_type="text/plain",
                kind=ArtifactKind.EVIDENCE,
            )
            if result.error is None:
                result = self._error_result(
                    "container.cleanup",
                    cleanup_message,
                    details={"verifier_status": result.status.value},
                    artifacts=(*result.artifacts, cleanup_artifact),
                )
            else:
                result = result.model_copy(
                    update={"artifacts": [*result.artifacts, cleanup_artifact]}
                )
        state = "completed" if cleanup.success else "residual"
        with self.state.transaction() as connection:
            connection.execute(
                "UPDATE container_executions SET state=?,result_json=?,cleanup_state=?,"
                "residual_effect=?,finished_at=?,updated_at=? WHERE execution_id=?",
                (
                    state,
                    result.model_dump_json(),
                    "succeeded" if cleanup.success else "failed",
                    cleanup.residual_effect,
                    timestamp(),
                    timestamp(),
                    str(row["execution_id"]),
                ),
            )
            self.state.enqueue_event(
                connection,
                "verifier.container.finished" if cleanup.success else "verifier.container.residual",
                str(row["run_id"]),
                node_id=str(row["node_id"]),
                attempt_id=str(row["attempt_id"]),
                payload={
                    "status": result.status.value,
                    "cleanup_state": "succeeded" if cleanup.success else "failed",
                    "residual_effect": cleanup.residual_effect,
                },
            )
        self._release_handle(str(row["handle"]) if row["handle"] else None)
        return VerifierOutcome(result)

    def _terminal_error(self, row: sqlite3.Row, code: str, message: str) -> VerifierOutcome:
        return self._finish(row, self._error_result(code, message))

    def _persist_uncertain(
        self, key: str, message: str, cleanup: ContainerCleanupResult
    ) -> VerifierOutcome:
        residual = cleanup.residual_effect if not cleanup.success else None
        artifacts: tuple[Artifact, ...] = ()
        if residual:
            artifacts = (
                self.artifacts.put_bytes(
                    self._redactor.redact(residual).encode("utf-8"),
                    media_type="text/plain",
                    kind=ArtifactKind.EVIDENCE,
                ),
            )
        result = self._error_result(
            "container.start_uncertain",
            "container start outcome is uncertain; refusing retry",
            details={
                "diagnostic": self._redactor.redact(message),
                "cleanup_success": cleanup.success,
            },
            artifacts=artifacts,
        )
        with self.state.transaction() as connection:
            connection.execute(
                "UPDATE container_executions SET state=?,result_json=?,residual_effect=?,"
                "cleanup_state=?,updated_at=? WHERE idempotency_key=?",
                (
                    "error" if cleanup.success else "uncertain",
                    result.model_dump_json(),
                    residual,
                    "succeeded" if cleanup.success else "failed",
                    timestamp(),
                    key,
                ),
            )
        return VerifierOutcome(result)

    def _persist_error(self, key: str, code: str, message: str) -> VerifierOutcome:
        result = self._error_result(code, message)
        with self.state.transaction() as connection:
            connection.execute(
                "UPDATE container_executions SET state='error',result_json=?,updated_at=? "
                "WHERE idempotency_key=?",
                (result.model_dump_json(), timestamp(), key),
            )
        return VerifierOutcome(result)

    def _mark_without_start(self, key: str, state: str) -> None:
        with self.state.transaction() as connection:
            connection.execute(
                "UPDATE container_executions SET state=?,updated_at=? WHERE idempotency_key=?",
                (state, timestamp(), key),
            )

    def _release_handle(self, handle: str | None) -> None:
        if handle is None:
            return
        with self._lock:
            if handle in self._active_handles:
                self._active_handles.remove(handle)
                self._slots.release()

    def _by_key(self, key: str) -> sqlite3.Row | None:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM container_executions WHERE idempotency_key=?", (key,)
            ).fetchone()
            return cast(sqlite3.Row | None, row)

    def _by_handle(self, handle: str) -> sqlite3.Row | None:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM container_executions WHERE handle=?", (handle,)
            ).fetchone()
            return cast(sqlite3.Row | None, row)

    def _error(
        self, code: str, message: str, *, kind: ErrorKind = ErrorKind.INFRASTRUCTURE
    ) -> VerifierOutcome:
        return VerifierOutcome(self._error_result(code, self._redactor.redact(message), kind=kind))

    @staticmethod
    def _error_result(
        code: str,
        message: str,
        *,
        kind: ErrorKind = ErrorKind.INFRASTRUCTURE,
        details: dict[str, object] | None = None,
        artifacts: tuple[Artifact, ...] = (),
    ) -> VerifierResult:
        error = Error(
            schema_version="1.0",
            kind=kind,
            code=code,
            message=message or "container infrastructure error",
            retryable=False,
            details=details or {},
        )
        return VerifierResult(
            schema_version="1.0",
            status=VerifierStatus.ERROR,
            summary=message or "container infrastructure error",
            artifacts=list(artifacts),
            error=error,
        )
