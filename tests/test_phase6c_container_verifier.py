from __future__ import annotations

import base64
import io
import json
import time
from collections import deque
from pathlib import Path
from typing import cast
from urllib.parse import quote

import pytest
from pydantic import ValidationError
from runtime_helpers import budget

from graph_engineering.delivery import DeliveryReportCompiler
from graph_engineering.models import ExecutionGraph, Node, VerifierResult
from graph_engineering.models.results import VerifierStatus
from graph_engineering.runtime import ArtifactStore, FakeExecutor, GraphRuntime, StateStore
from graph_engineering.verifier import (
    CapabilityViolation,
    ContainerAdapterCapabilities,
    ContainerArtifact,
    ContainerCleanupResult,
    ContainerExecutionSpec,
    ContainerImageAllowlist,
    ContainerImageIdentity,
    ContainerInspection,
    ContainerMount,
    ContainerNetworkPolicy,
    ContainerNetworkRule,
    ContainerPreflightError,
    ContainerPreflightKind,
    ContainerResourceLimits,
    ContainerRuntimeInfo,
    ContainerStartRequest,
    ContainerStartResult,
    ContainerStopResult,
    ContainerVerifier,
    DockerCLIAdapter,
    VerifierCapabilities,
    VerifierManifest,
    VerifierRequest,
)


class FakeContainerAdapter:
    def __init__(self) -> None:
        self.starts = 0
        self.inspections = 0
        self.stops = 0
        self.cleanups = 0
        self.requests: list[object] = []
        self.preflight_error: ContainerPreflightError | None = None
        self.start_uncertain = False
        self.cleanup_success = True
        self.cleanup_residual: str | None = None
        self.stop_settled = True
        self.results: deque[ContainerInspection] = deque()

    def preflight(self) -> ContainerRuntimeInfo:
        if self.preflight_error is not None:
            raise self.preflight_error
        return ContainerRuntimeInfo(
            runtime="fake",
            version="1.2.3",
            daemon_available=True,
            capabilities=ContainerAdapterCapabilities(
                streaming_output=True,
                exact_network_policy=True,
            ),
        )

    def start(self, request: object) -> ContainerStartResult:
        self.starts += 1
        self.requests.append(request)
        if self.start_uncertain:
            from graph_engineering.verifier import ContainerStartUncertainError

            raise ContainerStartUncertainError("ambiguous runtime response")
        return ContainerStartResult(handle=f"container-{self.starts}")

    def inspect(self, handle: str) -> ContainerInspection:
        self.inspections += 1
        if self.results:
            return self.results.popleft()
        return ContainerInspection(state="running")

    def stop(self, handle: str, timeout_seconds: float) -> ContainerStopResult:
        self.stops += 1
        return ContainerStopResult(
            settled=self.stop_settled,
            residual_effect=None if self.stop_settled else "container may still be running",
        )

    def cleanup(self, owner_id: str) -> ContainerCleanupResult:
        self.cleanups += 1
        return ContainerCleanupResult(
            success=self.cleanup_success,
            residual_effect=self.cleanup_residual,
        )


class CompletingContainerAdapter(FakeContainerAdapter):
    def inspect(self, handle: str) -> ContainerInspection:
        self.inspections += 1
        return ContainerInspection(state="succeeded", exit_code=0)


class ContainerRuntimeBridge:
    def __init__(self) -> None:
        self.provider: ContainerVerifier | None = None

    def execute(
        self,
        run_id: str,
        node: Node,
        attempt_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> VerifierResult:
        assert self.provider is not None
        return self.provider.execute(
            VerifierRequest(
                run_id=run_id,
                node_id=node.node_id,
                attempt_id=attempt_id,
                working_directory=self.provider.authorized_roots[0],
                artifact_directory=self.provider.authorized_roots[1],
                idempotency_key=idempotency_key,
                payload=dict(node.config),
            )
        ).result

    def query(self, handle: str) -> VerifierResult:
        assert self.provider is not None
        return self.provider.poll(handle).result

    def cancel(self, handle: str) -> VerifierResult:
        assert self.provider is not None
        return self.provider.cancel(handle).result


def image() -> ContainerImageIdentity:
    return ContainerImageIdentity(
        registry="registry.example.com",
        repository="graph/verifier",
        digest="sha256:" + "a" * 64,
        platform="linux/amd64",
        provenance={"builder": "ci", "source": "commit:123"},
    )


def spec(**updates: object) -> ContainerExecutionSpec:
    base: dict[str, object] = {
        "image": image(),
        "entrypoint": ("/verifier",),
        "resources": ContainerResourceLimits(
            cpu_count=1,
            memory_bytes=64 * 1024 * 1024,
            pids=32,
            timeout_seconds=30,
            max_stdout_bytes=1024,
            max_stderr_bytes=1024,
            max_artifact_bytes=2048,
            max_concurrency=1,
        ),
    }
    base.update(updates)
    return ContainerExecutionSpec.model_validate(base)


def manifest(container: ContainerExecutionSpec | None = None) -> VerifierManifest:
    return VerifierManifest(
        verifier_id="container-verifier",
        revision=1,
        verifier_type="project/container",
        runtime="container",
        entrypoint=("/verifier",),
        capabilities=VerifierCapabilities(secrets=("API_TOKEN",)),
        container=container or spec(secret_environment={"GE_SECRET_API_TOKEN": "API_TOKEN"}),
    )


def request(tmp_path: Path, *, key: str = "run:parallel:branch:node") -> VerifierRequest:
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts"
    workspace.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    return VerifierRequest(
        run_id="run-1",
        node_id="parallel:branch:verify",
        attempt_id="attempt-1",
        working_directory=workspace,
        artifact_directory=artifacts,
        idempotency_key=key,
    )


def provider(
    tmp_path: Path,
    adapter: FakeContainerAdapter,
    *,
    container: ContainerExecutionSpec | None = None,
    secrets: dict[str, str] | None = None,
    can_start: object | None = None,
) -> ContainerVerifier:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    return ContainerVerifier(
        manifest(container),
        ArtifactStore(tmp_path / "store"),
        state,
        adapter,
        image_allowlist=ContainerImageAllowlist(
            registries=("registry.example.com",),
            repositories=("graph/verifier",),
            digests=("sha256:" + "a" * 64,),
        ),
        authorized_roots=(tmp_path / "workspace", tmp_path / "artifacts"),
        secrets=secrets or {"API_TOKEN": "token-value"},
        can_start=can_start,  # type: ignore[arg-type]
    )


def test_mutable_tag_and_image_allowlist_are_rejected() -> None:
    with pytest.raises(ValueError, match="digest"):
        ContainerImageIdentity.model_validate(
            {
                "registry": "registry.example.com",
                "repository": "graph/verifier:latest",
                "platform": "linux/amd64",
                "provenance": {"builder": "ci"},
            }
        )
    with pytest.raises(CapabilityViolation, match="digest"):
        ContainerImageAllowlist(digests=("sha256:" + "b" * 64,)).require(image())


def test_versioned_container_manifest_fixtures_are_strict(load_fixture: object) -> None:
    assert callable(load_fixture)
    valid = VerifierManifest.model_validate(load_fixture("phase6c/container-manifest.json"))
    assert valid.container is not None
    assert valid.container.image.digest == "sha256:" + "a" * 64
    with pytest.raises(ValidationError):
        VerifierManifest.model_validate(load_fixture("phase6c/invalid-mutable-tag.json"))


def test_platform_provenance_and_frozen_config_drift_fail_before_start(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    drifted = spec(entrypoint=("/different",))
    verifier = provider(tmp_path, adapter)
    verifier._frozen_fingerprint = drifted.fingerprint()  # deliberate frozen-store drift fixture
    result = verifier.execute(request(tmp_path)).result
    assert result.status is VerifierStatus.ERROR
    assert result.error is not None and result.error.code == "container.config_drift"
    assert adapter.starts == 0
    with pytest.raises(ValueError, match="provenance"):
        ContainerImageIdentity(
            registry="registry.example.com",
            repository="graph/verifier",
            digest="sha256:" + "a" * 64,
            platform="linux/amd64",
            provenance={},
        )


@pytest.mark.parametrize("source", ("../escape", "/etc", r"C:\\Windows", r"..\\escape"))
def test_relative_and_absolute_mount_escape_is_rejected(source: str) -> None:
    with pytest.raises(ValueError, match=r"relative|traversal"):
        ContainerMount(source=source, target="/workspace")


def test_symlink_mount_escape_and_protected_writable_mount_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    link = workspace / "link"
    link.mkdir()
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda self: self == link or original_is_symlink(self),
    )
    adapter = FakeContainerAdapter()
    linked = spec(mounts=(ContainerMount(source="link", target="/workspace"),))
    result = provider(tmp_path, adapter, container=linked).execute(request(tmp_path)).result
    assert result.error is not None and result.error.code == "container.mount_policy"
    with pytest.raises(ValueError, match="read-only"):
        ContainerMount(source=".", target="/control", writable=True, classification="frozen")


def test_reparse_or_junction_mount_is_rejected_before_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    junction = workspace / "junction"
    junction.mkdir(parents=True)
    original_lstat = Path.lstat

    class ReparseStat:
        st_file_attributes = 0x400

        def __init__(self, wrapped: object) -> None:
            self.wrapped = wrapped

        def __getattr__(self, name: str) -> object:
            return getattr(self.wrapped, name)

    monkeypatch.setattr(
        Path,
        "lstat",
        lambda self: (
            ReparseStat(original_lstat(self)) if self == junction else original_lstat(self)
        ),
    )
    adapter = FakeContainerAdapter()
    mounted = spec(mounts=(ContainerMount(source="junction", target="/workspace"),))
    result = provider(tmp_path, adapter, container=mounted).execute(request(tmp_path)).result
    assert result.error is not None and result.error.code == "container.mount_policy"
    assert adapter.starts == 0


def test_docker_socket_system_and_home_mounts_are_rejected(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    for target in ("/var/run/docker.sock", "/etc", "/root"):
        mounted = spec(mounts=(ContainerMount(source=".", target=target),))
        result = provider(tmp_path, adapter, container=mounted).execute(request(tmp_path)).result
        assert result.error is not None and result.error.code == "container.mount_policy"
    assert adapter.starts == 0


def test_network_defaults_none_and_exact_policy_fails_closed_when_unenforceable(
    tmp_path: Path,
) -> None:
    assert spec().network.enabled is False
    adapter = FakeContainerAdapter()
    networked = spec(
        network=ContainerNetworkPolicy(
            enabled=True,
            allow=(ContainerNetworkRule(protocol="tcp", host="ci.example.com", port=443),),
        )
    )
    adapter.preflight = lambda: ContainerRuntimeInfo(  # type: ignore[method-assign]
        runtime="fake",
        version="1",
        daemon_available=True,
        capabilities=ContainerAdapterCapabilities(streaming_output=True),
    )
    result = provider(tmp_path, adapter, container=networked).execute(request(tmp_path)).result
    assert result.error is not None and result.error.code == "container.network_policy"
    assert adapter.starts == 0
    with pytest.raises(ValueError):
        ContainerNetworkRule(protocol="tcp", host="*.example.com", port=443)


def test_preflight_errors_are_typed_and_do_not_start(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    adapter.preflight_error = ContainerPreflightError(
        ContainerPreflightKind.DAEMON_UNAVAILABLE, "daemon unavailable"
    )
    result = provider(tmp_path, adapter).execute(request(tmp_path)).result
    assert result.status is VerifierStatus.ERROR
    assert result.error is not None
    assert result.error.code == "container.preflight.daemon_unavailable"
    assert adapter.starts == 0


def test_restart_queries_checkpointed_handle_and_completed_result_is_reused(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    verifier = provider(tmp_path, adapter)
    first = verifier.execute(request(tmp_path)).result
    assert first.status is VerifierStatus.PENDING and first.external_handle == "container-1"
    adapter.results.append(ContainerInspection(state="succeeded", exit_code=0))
    second = verifier.execute(request(tmp_path)).result
    third = verifier.execute(request(tmp_path)).result
    assert second.status is third.status is VerifierStatus.PASSED
    assert adapter.starts == 1
    assert adapter.inspections == 1


def test_cpu_memory_pid_and_platform_limits_reach_adapter_without_shell_source(
    tmp_path: Path,
) -> None:
    adapter = FakeContainerAdapter()
    verifier = provider(tmp_path, adapter)
    verifier.execute(request(tmp_path))
    started = cast(ContainerStartRequest, adapter.requests[0])
    assert started.resources.cpu_count == 1
    assert started.resources.memory_bytes == 64 * 1024 * 1024
    assert started.resources.pids == 32
    assert started.platform == "linux/amd64"
    assert started.entrypoint == ("/verifier",)


def test_uncertain_start_never_retriggers(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    adapter.start_uncertain = True
    verifier = provider(tmp_path, adapter)
    first = verifier.execute(request(tmp_path)).result
    second = verifier.execute(request(tmp_path)).result
    assert first.error is not None and first.error.code == "container.start_uncertain"
    assert second.error is not None and second.error.code == "container.start_uncertain"
    assert adapter.starts == 1


def test_streaming_output_secret_redaction_limits_and_artifacts(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    secret = "overlap secret/?"
    verifier = provider(tmp_path, adapter, secrets={"API_TOKEN": secret})
    verifier.execute(request(tmp_path))
    encoded = quote(secret, safe="").encode()
    base64_secret = base64.b64encode(secret.encode()).decode().encode()
    adapter.results.append(
        ContainerInspection(
            state="succeeded",
            exit_code=0,
            stdout_chunks=(b"prefix overlap ", b"secret/? suffix ", encoded),
            stderr_chunks=(base64_secret,),
            artifacts=(ContainerArtifact("result.txt", secret.encode()),),
        )
    )
    result = verifier.poll("container-1").result
    assert result.status is VerifierStatus.PASSED
    for artifact in result.artifacts:
        content = (tmp_path / "store" / artifact.uri).read_bytes()
        assert secret.encode() not in content
        assert encoded not in content
        assert base64_secret not in content


def test_wall_clock_timeout_requests_bounded_stop(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    timed = spec(
        resources=ContainerResourceLimits(
            cpu_count=1,
            memory_bytes=1024,
            pids=2,
            timeout_seconds=0.001,
            max_stdout_bytes=4,
            max_stderr_bytes=4,
            max_artifact_bytes=4,
            max_concurrency=1,
        )
    )
    verifier = provider(tmp_path, adapter, container=timed)
    verifier.execute(request(tmp_path))
    time.sleep(0.01)
    result = verifier.poll("container-1").result
    assert result.error is not None and result.error.code == "container.timeout"
    assert adapter.stops == 1


def test_output_limit_stops_container_and_is_infrastructure_error(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    limited = spec(
        resources=ContainerResourceLimits(
            cpu_count=1,
            memory_bytes=1024,
            pids=2,
            timeout_seconds=1,
            max_stdout_bytes=4,
            max_stderr_bytes=4,
            max_artifact_bytes=4,
            max_concurrency=1,
        )
    )
    verifier = provider(tmp_path, adapter, container=limited)
    verifier.execute(request(tmp_path))
    adapter.results.append(ContainerInspection(state="running", stdout_chunks=(b"123", b"45")))
    result = verifier.poll("container-1").result
    assert result.error is not None and result.error.code == "container.output_limit"
    assert adapter.stops == 1


def test_docker_log_reader_bounds_each_stream_during_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = io.BytesIO(b"unbounded-stdout")
            self.stderr = io.BytesIO(b"unbounded-stderr")
            self.terminated = 0

        def terminate(self) -> None:
            self.terminated += 1

        def kill(self) -> None:
            self.terminated += 1

        def wait(self, timeout: float) -> int:
            return 0

    process = FakeProcess()
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: process)
    stdout, stderr = DockerCLIAdapter._bounded_logs(["docker", "logs", "handle"], 4, 5)
    assert stdout == b"unbou"
    assert stderr == b"unboun"
    assert process.terminated >= 1


def test_barrier_cancel_cleanup_failure_and_residual_are_distinct(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    blocked = provider(tmp_path, adapter, can_start=lambda: False)
    barrier = blocked.execute(request(tmp_path)).result
    assert barrier.error is not None and barrier.error.code == "container.barrier"
    assert adapter.starts == 0

    active = provider(tmp_path / "active", adapter)
    active.execute(request(tmp_path / "active"))
    adapter.stop_settled = False
    adapter.cleanup_success = False
    adapter.cleanup_residual = "owned volume remains"
    cancelled = active.cancel("container-1").result
    assert cancelled.status is VerifierStatus.ERROR
    assert cancelled.error is not None and cancelled.error.code == "container.residual_effect"
    assert cancelled.artifacts
    assert adapter.stops == 1 and adapter.cleanups == 1


def test_verifier_failure_and_cleanup_failure_are_not_conflated(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    verifier = provider(tmp_path, adapter)
    verifier.execute(request(tmp_path))
    adapter.results.append(ContainerInspection(state="failed", exit_code=7))
    failed = verifier.poll("container-1").result
    assert failed.status is VerifierStatus.FAILED

    tmp2 = tmp_path / "cleanup"
    adapter2 = FakeContainerAdapter()
    adapter2.cleanup_success = False
    adapter2.cleanup_residual = "temporary network remains"
    verifier2 = provider(tmp2, adapter2)
    verifier2.execute(request(tmp2))
    adapter2.results.append(ContainerInspection(state="succeeded", exit_code=0))
    cleanup = verifier2.poll("container-1").result
    assert cleanup.status is VerifierStatus.ERROR
    assert cleanup.error is not None and cleanup.error.code == "container.cleanup"


def test_concurrency_limit_rejects_pending_start(tmp_path: Path) -> None:
    adapter = FakeContainerAdapter()
    verifier = provider(tmp_path, adapter)
    first = verifier.execute(request(tmp_path, key="effect-1")).result
    second = verifier.execute(request(tmp_path, key="effect-2")).result
    assert first.status is VerifierStatus.PENDING
    assert second.error is not None and second.error.code == "container.concurrency"
    assert adapter.starts == 1


def test_parallel_branches_use_qualified_container_identity_and_settle(
    tmp_path: Path, load_fixture: object
) -> None:
    assert callable(load_fixture)
    graph_data = load_fixture("phase6b/parallel-graph.yaml")
    for branch in graph_data["nodes"][0]["parallel"]["branches"]:
        branch["subgraph"]["nodes"][0]["node_type"] = "verifier"
        branch["subgraph"]["nodes"][0]["config"] = {"external": True}
    graph = ExecutionGraph.model_validate(graph_data)
    root = tmp_path / "runtime"
    bridge = ContainerRuntimeBridge()
    runtime = GraphRuntime(root, executor=FakeExecutor(), verifier=bridge)
    workspace = tmp_path / "workspace"
    artifact_dir = tmp_path / "provider-artifacts"
    workspace.mkdir()
    artifact_dir.mkdir()
    adapter = CompletingContainerAdapter()
    parallel_spec = spec(
        resources=ContainerResourceLimits(
            cpu_count=1,
            memory_bytes=64 * 1024 * 1024,
            pids=32,
            timeout_seconds=30,
            max_stdout_bytes=1024,
            max_stderr_bytes=1024,
            max_artifact_bytes=2048,
            max_concurrency=2,
        ),
        secret_environment={"GE_SECRET_API_TOKEN": "API_TOKEN"},
    )
    bridge.provider = ContainerVerifier(
        manifest(parallel_spec),
        ArtifactStore(artifact_dir),
        runtime.state,
        adapter,
        image_allowlist=ContainerImageAllowlist(
            registries=("registry.example.com",),
            repositories=("graph/verifier",),
            digests=("sha256:" + "a" * 64,),
        ),
        authorized_roots=(workspace, artifact_dir),
        secrets={"API_TOKEN": "token-value"},
    )
    runtime.create_run("run-1", "project", graph, "6" * 64, budget())
    runtime.run("run-1")
    assert runtime.snapshot("run-1").run_status.value == "succeeded"
    assert adapter.starts == 2
    with runtime.state.read_connection() as connection:
        rows = list(
            connection.execute(
                "SELECT idempotency_key,state,cleanup_state FROM container_executions "
                "ORDER BY idempotency_key"
            )
        )
    assert len(rows) == 2
    assert all(row["state"] == "completed" and row["cleanup_state"] == "succeeded" for row in rows)
    assert any("alpha" in row["idempotency_key"] for row in rows)
    assert any("beta" in row["idempotency_key"] for row in rows)


def test_migration_9_is_repeatable_and_preserves_compatibility(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    state.migrate()
    assert state.container_migration_version == 9
    assert state.parallel_migration_version == 8
    assert state.service_migration_version == 7
    with state.read_connection() as connection:
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations")]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(container_executions)")}
    assert versions == list(range(1, 10))
    assert {"owner_id", "handle", "image_digest", "config_fingerprint", "cleanup_state"} <= columns


def test_final_delivery_report_discloses_container_cleanup_residual(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    now = "2026-08-24T00:00:00Z"
    with state.transaction() as connection:
        connection.execute(
            "INSERT INTO delivery_terminal_fixtures(run_id,contract_id,contract_revision,status,"
            "reason,created_at) VALUES ('run-1','contract-1',1,'error','execution_error',?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO container_executions(execution_id,run_id,node_id,attempt_id,"
            "idempotency_key,owner_id,state,handle,image_digest,config_fingerprint,stdout_bytes,"
            "stderr_bytes,artifact_bytes,cleanup_state,residual_effect,created_at,updated_at) "
            "VALUES ('execution-1','run-1','verify','attempt-1','effect-1','owner-1','residual',"
            "'container-1',?,?,0,0,0,'failed','owned volume remains',?,?)",
            ("sha256:" + "a" * 64, "b" * 64, now, now),
        )
    artifacts = ArtifactStore(tmp_path / "artifacts")
    compiler = DeliveryReportCompiler(state, artifacts, tmp_path / "reports")
    compiler.compile("run-1")
    effects = json.loads(
        (tmp_path / "reports/run-1/1/external-effects.json").read_text(encoding="utf-8")
    )
    assert effects["effects"][0]["cleanup_state"] == "failed"
    assert effects["effects"][0]["residual_effect"] == "owned volume remains"
