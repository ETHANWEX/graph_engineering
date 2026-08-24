from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from runtime_helpers import budget, graph

from graph_engineering.delivery import (
    CheckConclusion,
    DeliveryReportCompiler,
    GitHubChecksProvider,
    GitHubRepository,
    HumanDecisionService,
)
from graph_engineering.mcp_server import MCPServer
from graph_engineering.models import ExecutorResult, HumanMessage
from graph_engineering.models.graph import NodeType
from graph_engineering.models.results import ExecutorStatus
from graph_engineering.observability import (
    ExportResult,
    InMemoryExporter,
    NoOpTelemetryProvider,
    ObservabilityCompatibilityError,
    ObservabilityConfig,
    SpanRecord,
    TelemetryDependencyMissing,
    TelemetryIdentity,
    TelemetryProvider,
    load_optional_exporter,
)
from graph_engineering.review import ReviewFixCoordinator, ReviewResult, ReviewVerdict
from graph_engineering.runtime import (
    ArtifactStore,
    FakeExecutor,
    FakeVerifier,
    GraphRuntime,
    StateStore,
)
from graph_engineering.service import HumanGateway, RuntimeService, ServiceClient
from graph_engineering.verifier.http_pipeline import HttpResponse


def _provider(
    exporter: InMemoryExporter | None = None,
    **updates: Any,
) -> tuple[TelemetryProvider, InMemoryExporter]:
    exporter = exporter or InMemoryExporter()
    config = ObservabilityConfig(enabled=True, **updates)
    values = iter(range(1_000, 10_000))
    return TelemetryProvider(config, exporter, clock_ns=lambda: next(values)), exporter


def _spans(exporter: InMemoryExporter) -> list[SpanRecord]:
    return [record for record in exporter.records if isinstance(record, SpanRecord)]


def test_trace_parent_links_and_restart_identity_are_deterministic() -> None:
    provider, exporter = _provider()
    identity = TelemetryIdentity(repository_id="repo-1", run_id="run-1")
    link = provider.link(TelemetryIdentity(run_id="run-1", branch_id="alpha"))
    with provider.span(
        "ge.runtime.run",
        identity,
        {"ge.component": "runtime", "ge.operation": "run"},
    ) as root:
        with provider.span(
            "ge.runtime.node",
            TelemetryIdentity(run_id="run-1", node_id="implement", attempt_id="attempt-1"),
            {"ge.component": "runtime", "ge.operation": "node"},
            links=(link,),
        ) as child:
            child.set_result("succeeded")
        root.set_result("succeeded", terminal=True)
    assert provider.force_flush()
    spans = _spans(exporter)
    assert [item.name for item in spans] == ["ge.runtime.node", "ge.runtime.run"]
    assert spans[0].parent_span_id == spans[1].span_id
    assert spans[0].trace_id == spans[1].trace_id and len(spans[0].trace_id) == 32
    assert spans[0].links == (link,)

    restarted, restarted_exporter = _provider()
    with restarted.span(
        "ge.runtime.recovery",
        identity,
        {"ge.component": "runtime", "ge.operation": "recover", "ge.recovered": True},
        links=(restarted.link(identity),),
    ):
        pass
    assert restarted.force_flush()
    assert _spans(restarted_exporter)[0].trace_id == spans[1].trace_id


def test_deterministic_sampling_buffer_overflow_and_late_telemetry() -> None:
    provider, exporter = _provider(
        sampling_numerator=0,
        sampling_denominator=1,
        buffer_capacity=4,
        batch_size=2,
    )
    with provider.span("ge.runtime.run", TelemetryIdentity(run_id="run-1")):
        pass
    assert provider.force_flush() and _spans(exporter) == []

    sampled, sampled_exporter = _provider(buffer_capacity=4, batch_size=2)
    sampled.mark_run_terminal("run-1")
    for number in range(5):
        with sampled.span(
            "ge.runtime.node",
            TelemetryIdentity(run_id="run-1", node_id=f"node-{number}"),
            {"ge.component": "runtime", "ge.operation": "node"},
        ):
            pass
    assert sampled.health().dropped > 0
    sampled.force_flush()
    late = _spans(sampled_exporter)
    assert late and all(dict(item.attributes)["ge.late"] is True for item in late)


def test_export_timeout_partial_failure_and_exception_are_isolated() -> None:
    for exporter in (
        InMemoryExporter(delay_seconds=0.05),
        InMemoryExporter(result=ExportResult("partial", accepted=1)),
        InMemoryExporter(exception=True),
    ):
        provider, _ = _provider(
            exporter,
            export_timeout_seconds=0.005,
            flush_timeout_seconds=0.02,
        )
        with provider.span(
            "ge.runtime.run",
            TelemetryIdentity(run_id="run-1"),
            {"ge.component": "runtime", "ge.operation": "run"},
        ):
            pass
        assert provider.force_flush() is False
        health = provider.health()
        assert health.export_timeouts or health.partial_failures or health.export_failures


def test_secret_high_cardinality_and_unrestricted_bodies_are_rejected() -> None:
    secret = "token/value+overlap"
    provider = TelemetryProvider(
        ObservabilityConfig(enabled=True),
        InMemoryExporter(),
        secret_values=(secret,),
    )
    unsafe = (
        {"authorization": "redacted"},
        {"ge.result": secret},
        {"ge.result": "token%2Fvalue%2Boverlap"},
        {"ge.result": "dG9rZW4vdmFsdWUrb3ZlcmxhcA=="},
        {"ge.result": "https://collector.example.invalid/path"},
    )
    for attributes in unsafe:
        before = provider.health().rejected
        with provider.span("ge.runtime.run", attributes=attributes):
            pass
        assert provider.health().rejected == before + 1
    provider.metric("ge.operation.result", 1, labels={"run_id": "run-1"})
    assert provider.health().rejected == len(unsafe) + 1
    provider.metric(
        "ge.operation.result",
        1,
        labels={"component": "runtime", "operation": "user-supplied-operation"},
    )
    assert provider.health().rejected == len(unsafe) + 2


def test_disabled_provider_preserves_runtime_behavior(tmp_path: Path) -> None:
    executor = FakeExecutor(
        {
            "one": [
                ExecutorResult(schema_version="1.0", status=ExecutorStatus.SUCCEEDED, summary="ok")
            ]
        }
    )
    runtime = GraphRuntime(
        tmp_path,
        executor=executor,
        verifier=FakeVerifier(),
        telemetry=NoOpTelemetryProvider(),
    )
    # The fixture path is stable and ignored; use a unique Run and no external effect.
    run_id = f"run-disabled-{datetime.now(UTC).timestamp()}"
    runtime.create_run(
        run_id,
        "project",
        graph([("one", NodeType.AGENT, None)], []),
        "b" * 64,
        budget(),
    )
    assert runtime.run(run_id).value == "succeeded"


def test_runtime_instrumentation_covers_node_verifier_and_failure_isolation(tmp_path: Path) -> None:
    provider, exporter = _provider()
    runtime = GraphRuntime(
        tmp_path,
        executor=FakeExecutor(
            {
                "one": [
                    ExecutorResult(
                        schema_version="1.0",
                        status=ExecutorStatus.SUCCEEDED,
                        summary="ok",
                    )
                ]
            }
        ),
        verifier=FakeVerifier(),
        telemetry=provider,
    )
    definition = graph([("one", NodeType.AGENT, None)], [])
    runtime.create_run("run-1", "project", definition, "b" * 64, budget())
    assert runtime.run("run-1").value == "succeeded"
    assert provider.force_flush()
    names = {item.name for item in _spans(exporter)}
    assert {"ge.runtime.run", "ge.runtime.node", "ge.executor.invocation"} <= names

    failing, _ = _provider(InMemoryExporter(exception=True))
    unaffected = GraphRuntime(
        tmp_path / "failure",
        executor=FakeExecutor(
            {
                "one": [
                    ExecutorResult(
                        schema_version="1.0",
                        status=ExecutorStatus.SUCCEEDED,
                        summary="ok",
                    )
                ]
            }
        ),
        verifier=FakeVerifier(),
        telemetry=failing,
    )
    unaffected.create_run("run-2", "project", definition, "b" * 64, budget())
    assert unaffected.run("run-2").value == "succeeded"
    assert failing.force_flush() is False


def test_service_mcp_review_report_and_human_instrumentation_are_non_authoritative(
    tmp_path: Path,
) -> None:
    provider, exporter = _provider()
    gateway = HumanGateway(tmp_path, "project", telemetry=provider)
    started = gateway.dispatch("start", {"project_id": "project", "actor_id": "human"})
    assert started["project_id"] == "project"
    # MCP validation errors never become business state or leak request bodies.
    server = MCPServer(tmp_path, telemetry=provider)
    rejected = server.handle({"jsonrpc": "2.0", "id": 1, "method": "missing"})
    assert rejected and rejected["error"]["code"] == -32601

    calls: list[str] = []
    review = ReviewFixCoordinator(
        review=lambda attempt: ReviewResult(verdict=ReviewVerdict.APPROVED, summary=str(attempt)),
        implement_fix=lambda _findings: calls.append("fix"),
        run_affected_verifiers=lambda _findings: calls.append("verify"),
        telemetry=provider,
        run_id="run-1",
    )
    assert review.run().verdict is ReviewVerdict.APPROVED

    state = StateStore(tmp_path / "report.db")
    state.migrate()
    now = "2026-08-25T00:00:00Z"
    with state.transaction() as connection:
        connection.execute(
            "INSERT INTO delivery_terminal_fixtures(run_id,contract_id,contract_revision,status,"
            "reason,created_at) VALUES ('run-1','contract-1',1,'failed','implementation_failed',?)",
            (now,),
        )
    compiler = DeliveryReportCompiler(
        state,
        ArtifactStore(tmp_path / "artifacts"),
        tmp_path / "reports",
        telemetry=provider,
    )
    assert compiler.compile("run-1").revision == 1
    assert provider.force_flush()
    names = {item.name for item in _spans(exporter)}
    assert {
        "ge.service.operation",
        "ge.mcp.request",
        "ge.review.attempt",
        "ge.report.generate",
    } <= names
    # Telemetry never enters the Runtime/control SQLite schema.
    with sqlite3.connect(tmp_path / ".ge" / "control" / "phase3.db") as connection:
        assert not any(
            row[0].startswith("telemetry")
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )


def test_optional_dependency_mismatch_flush_shutdown_and_async_thread_boundaries() -> None:
    with pytest.raises(TelemetryDependencyMissing):
        load_optional_exporter("graph_engineering_missing_otel_exporter")
    incompatible = InMemoryExporter()
    incompatible.contract_version = "2.0"
    with pytest.raises(ObservabilityCompatibilityError):
        TelemetryProvider(ObservabilityConfig(enabled=True), incompatible)

    provider, exporter = _provider()
    root_identity = TelemetryIdentity(repository_id="repo", run_id="run-1")

    async def child() -> None:
        with provider.span(
            "ge.runtime.node",
            TelemetryIdentity(run_id="run-1", node_id="async"),
            {"ge.component": "runtime", "ge.operation": "node"},
        ):
            await asyncio.sleep(0)

    with provider.span(
        "ge.runtime.run",
        root_identity,
        {"ge.component": "runtime", "ge.operation": "run"},
    ):
        asyncio.run(child())
        link = provider.link(TelemetryIdentity(run_id="run-1", branch_id="thread"))

        def threaded() -> None:
            with provider.span(
                "ge.runtime.parallel_branch",
                TelemetryIdentity(run_id="run-1", branch_id="thread"),
                {"ge.component": "runtime", "ge.operation": "parallel_branch"},
                links=(link,),
            ):
                pass

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(threaded).result()
    assert provider.shutdown()
    spans = _spans(exporter)
    async_span = next(item for item in spans if dict(item.attributes).get("ge.node.id") == "async")
    thread_span = next(
        item for item in spans if dict(item.attributes).get("ge.branch.id") == "thread"
    )
    assert async_span.parent_span_id is not None
    assert thread_span.parent_span_id is None and thread_span.links == (link,)
    assert provider.health().shutdown is True


def test_concurrent_equal_identity_spans_receive_unique_span_ids() -> None:
    provider, exporter = _provider()
    identity = TelemetryIdentity(repository_id="repo", run_id="run-1", node_id="same")
    entered = threading.Barrier(3)
    release = threading.Event()

    def record() -> None:
        with provider.span(
            "ge.runtime.node",
            identity,
            {"ge.component": "runtime", "ge.operation": "node"},
        ):
            entered.wait()
            release.wait(timeout=2)

    threads = [threading.Thread(target=record) for _ in range(2)]
    for thread in threads:
        thread.start()
    entered.wait()
    release.set()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    assert provider.force_flush()
    span_ids = [span.span_id for span in _spans(exporter)]
    assert len(span_ids) == 2
    assert len(set(span_ids)) == 2


def test_parallel_read_only_and_github_instrumentation(
    tmp_path: Path, load_fixture: object
) -> None:
    from graph_engineering.models import ExecutionGraph

    assert callable(load_fixture)
    provider, exporter = _provider()
    definition = ExecutionGraph.model_validate(load_fixture("phase6b/parallel-graph.yaml"))
    executor = FakeExecutor(
        {
            "fanout.alpha.work": [
                ExecutorResult(
                    schema_version="1.0", status=ExecutorStatus.SUCCEEDED, summary="alpha"
                )
            ],
            "fanout.beta.work": [
                ExecutorResult(
                    schema_version="1.0", status=ExecutorStatus.SUCCEEDED, summary="beta"
                )
            ],
        }
    )
    run_root = tmp_path / ".ge" / "runs" / "run-1"
    runtime = GraphRuntime(
        run_root,
        executor=executor,
        verifier=FakeVerifier(),
        telemetry=provider,
    )
    runtime.create_run("run-1", "project", definition, "b" * 64, budget())
    assert runtime.run("run-1").value == "succeeded"
    fingerprint = runtime.snapshot("run-1").execution_fingerprint()
    with runtime.state.read_connection() as connection:
        outbox = connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0]

    gateway = HumanGateway(tmp_path, "project", telemetry=provider)
    assert gateway.status({"run_id": "run-1"})["status"] == "succeeded"
    assert runtime.snapshot("run-1").execution_fingerprint() == fingerprint
    with runtime.state.read_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0] == outbox

    class Transport:
        def request(
            self,
            method: str,
            url: str,
            headers: Mapping[str, str],
            body: bytes | None,
            timeout: float,
        ) -> HttpResponse:
            del method, url, headers, body, timeout
            payload = {
                "check_runs": [
                    {
                        "id": 1,
                        "head_sha": "a" * 40,
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            }
            return HttpResponse(200, {}, json.dumps(payload).encode())

    checks = GitHubChecksProvider(
        GitHubRepository(owner="acme", name="service", api_base_url="https://api.github.test"),
        transport=Transport(),
        allowed_hosts=("api.github.test",),
        telemetry=provider,
    ).status("a" * 40)
    assert checks.checks[0].conclusion is CheckConclusion.SUCCESS
    assert provider.force_flush()
    names = [item.name for item in _spans(exporter)]
    assert "ge.runtime.parallel_branch" in names
    assert "ge.github.operation" in names
    branch_spans = [item for item in _spans(exporter) if item.name == "ge.runtime.parallel_branch"]
    assert {dict(item.attributes)["ge.branch.id"] for item in branch_spans} == {"alpha", "beta"}


def test_actual_ipc_and_durable_agent_session_instrumentation(tmp_path: Path) -> None:
    from graph_engineering.executor import (
        DurableExecutorRuntime,
        ExecutorCapabilities,
        ExecutorEvent,
        ExecutorOutcome,
        ExecutorRequest,
        ExecutorRole,
        SandboxMode,
        SessionHandle,
    )
    from graph_engineering.models.common import ArtifactKind
    from graph_engineering.runtime.sessions import SessionRepository

    provider, exporter = _provider()
    service = RuntimeService(tmp_path, "project", telemetry=provider)
    thread = threading.Thread(target=service.serve, daemon=True)
    thread.start()
    for _ in range(200):
        if service.endpoint_path.is_file():
            break
        time.sleep(0.01)
    assert ServiceClient(tmp_path).call("health")["healthy"] is True
    ServiceClient(tmp_path).call("shutdown")
    thread.join(timeout=5)
    assert not thread.is_alive()

    artifacts = ArtifactStore(tmp_path / "agent-artifacts")

    class Adapter:
        starts = 0

        def capabilities(self) -> ExecutorCapabilities:
            return ExecutorCapabilities(
                "fake", "1.0", True, True, True, True, True, True, True, True, True
            )

        def start(self, request: ExecutorRequest) -> ExecutorOutcome:
            del request
            self.starts += 1
            raw = artifacts.put_bytes(b"{}", kind=ArtifactKind.LOG)
            return ExecutorOutcome(
                SessionHandle("fake", "session-1", "1.0"),
                ExecutorResult(
                    schema_version="1.0", status=ExecutorStatus.SUCCEEDED, summary="done"
                ),
                (ExecutorEvent("session_started", "session", "session-1", {}),),
                raw,
                None,
                0,
            )

        def resume(self, session: SessionHandle, request: ExecutorRequest) -> ExecutorOutcome:
            del session
            return self.start(request)

        def review(self, request: ExecutorRequest) -> ExecutorOutcome:
            return self.start(request)

        def cancel(self, session: SessionHandle, *, grace_seconds: float = 5) -> bool:
            del session, grace_seconds
            return True

    state = StateStore(tmp_path / "agent.db")
    sessions = SessionRepository(state)
    sessions.ensure_run_fixture("run-agent")
    request = ExecutorRequest(
        "run-agent",
        "implement",
        "attempt-1",
        ExecutorRole.IMPLEMENTER,
        "implement",
        "bounded context",
        tmp_path,
        SandboxMode.WORKSPACE_WRITE,
        {},
        tmp_path / "control",
    )
    adapter = Adapter()
    runtime = DurableExecutorRuntime(adapter, sessions, telemetry=provider)
    assert runtime.execute(request).result.status is ExecutorStatus.SUCCEEDED
    assert runtime.execute(request).result.status is ExecutorStatus.SUCCEEDED
    assert adapter.starts == 1
    assert provider.force_flush()
    spans = _spans(exporter)
    assert any(item.name == "ge.ipc.request" for item in spans)
    agent = [item for item in spans if item.name == "ge.executor.invocation"]
    assert len(agent) == 2
    assert all(dict(item.attributes)["ge.session.id"] == "session-1" for item in agent)


def test_container_cleanup_span_uses_persisted_effect_identity(tmp_path: Path) -> None:
    from test_phase6c_container_verifier import (
        CompletingContainerAdapter,
        manifest,
        request,
    )

    from graph_engineering.verifier.container import ContainerVerifier
    from graph_engineering.verifier.types import ContainerImageAllowlist

    provider, exporter = _provider()
    state = StateStore(tmp_path / "state.db")
    verifier = ContainerVerifier(
        manifest(),
        ArtifactStore(tmp_path / "store"),
        state,
        CompletingContainerAdapter(),
        image_allowlist=ContainerImageAllowlist(
            registries=("registry.example.com",),
            repositories=("graph/verifier",),
            digests=("sha256:" + "a" * 64,),
        ),
        authorized_roots=(tmp_path / "workspace", tmp_path / "artifacts"),
        secrets={"API_TOKEN": "token-value"},
        telemetry=provider,
    )
    result = verifier.execute(request(tmp_path, key="effect-1"))
    assert result.result.external_handle == "container-1"
    result = verifier.poll("container-1")
    assert result.result.status.value == "passed"
    assert provider.force_flush()
    cleanup = next(item for item in _spans(exporter) if item.name == "ge.runtime.cleanup")
    attributes = dict(cleanup.attributes)
    assert attributes["ge.run.id"] == "run-1"
    assert attributes["ge.external.effect.id"] == "effect-1"
    assert attributes["ge.provider.handle.id"] == "container-1"


def test_human_decision_span_never_changes_accept_never_merge(tmp_path: Path) -> None:
    provider, exporter = _provider()
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    with state.transaction() as connection:
        connection.execute(
            "INSERT INTO delivery_terminal_fixtures(run_id,contract_id,contract_revision,status,"
            "reason,created_at) VALUES ('run-1','contract-1',1,'succeeded','completed',?)",
            (datetime.now(UTC).isoformat(),),
        )
    message = HumanMessage(
        schema_version="1.0",
        message_id="decision-1",
        actor_id="human",
        project_id="project",
        run_id="run-1",
        content="confirm accept run-1",
        created_at=datetime.now(UTC),
    )
    accepted = HumanDecisionService(state, telemetry=provider).accept(message, report_revision=1)
    assert accepted.merge_performed is False
    assert provider.force_flush()
    span = next(item for item in _spans(exporter) if item.name == "ge.human.decision")
    assert dict(span.attributes)["ge.action"] == "accept"
