from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from runtime_helpers import budget, graph, status_is

from graph_engineering.models import (
    Error,
    ExecutionGraph,
    ExecutorResult,
    VerifierResult,
)
from graph_engineering.models.common import ErrorKind
from graph_engineering.models.graph import NodeType
from graph_engineering.models.reports import TerminalReason, TerminalStatus
from graph_engineering.models.results import ExecutorStatus, VerifierStatus
from graph_engineering.runtime import FakeExecutor, FakeVerifier, GraphRuntime

CONTRACT_HASH = "a" * 64


def executor_result(status: ExecutorStatus, summary: str = "done") -> ExecutorResult:
    return ExecutorResult(
        schema_version="1.0",
        status=status,
        summary=summary,
        failure_reason="implementation failed" if status is ExecutorStatus.FAILED else None,
        error=(
            Error(
                schema_version="1.0",
                kind=ErrorKind.EXECUTOR,
                code="executor.crashed",
                message="crashed",
                retryable=False,
            )
            if status is ExecutorStatus.ERROR
            else None
        ),
    )


def verifier_result(status: VerifierStatus) -> VerifierResult:
    return VerifierResult(
        schema_version="1.0",
        status=status,
        summary=status.value,
        failure_details=["acceptance failed"] if status is VerifierStatus.FAILED else [],
        error=(
            Error(
                schema_version="1.0",
                kind=ErrorKind.VERIFIER,
                code="verifier.unavailable",
                message="unavailable",
                retryable=False,
            )
            if status is VerifierStatus.ERROR
            else None
        ),
    )


def test_fake_executor_completes_a_serial_graph(tmp_path: Path) -> None:
    definition = graph(
        [("implement", NodeType.AGENT, None), ("verify", NodeType.VERIFIER, None)],
        [("implement", "verify", None, None)],
    )
    executor = FakeExecutor({"implement": [executor_result(ExecutorStatus.SUCCEEDED)]})
    verifier = FakeVerifier({"verify": [verifier_result(VerifierStatus.PASSED)]})
    runtime = GraphRuntime(tmp_path, executor=executor, verifier=verifier)
    runtime.create_run("run-1", "project-1", definition, CONTRACT_HASH, budget())

    assert runtime.run("run-1") is TerminalStatus.SUCCEEDED
    assert [call.node_id for call in executor.calls] == ["implement"]
    assert [call.node_id for call in verifier.calls] == ["verify"]
    assert runtime.final_report("run-1").terminal_reason is TerminalReason.COMPLETED
    with runtime.state.read_connection() as connection:
        attempts = list(
            connection.execute("SELECT attempt_id, status FROM attempts ORDER BY attempt_id")
        )
    assert [(row["attempt_id"], row["status"]) for row in attempts] == [
        ("run-1:implement:1", "succeeded"),
        ("run-1:verify:1", "succeeded"),
    ]


def test_phase_1_fixture_completes_serial_graph(
    tmp_path: Path, load_fixture: Callable[[str], Any]
) -> None:
    definition = ExecutionGraph.model_validate(load_fixture("runtime/serial-graph.yaml"))
    scripts = load_fixture("runtime/fake-results.json")
    runtime = GraphRuntime(
        tmp_path,
        executor=FakeExecutor({"implement": [ExecutorResult.model_validate(scripts["executor"])]}),
        verifier=FakeVerifier({"verify": [VerifierResult.model_validate(scripts["verifier"])]}),
    )
    runtime.create_run("run-fixture", "project", definition, CONTRACT_HASH, budget())

    assert runtime.run("run-fixture") is TerminalStatus.SUCCEEDED


def test_failed_implementation_enters_repair_loop(tmp_path: Path) -> None:
    definition = graph(
        [
            ("implement", NodeType.AGENT, None),
            ("verify", NodeType.VERIFIER, None),
            ("repair", NodeType.AGENT, None),
            ("deliver", NodeType.DELIVERY, None),
        ],
        [
            ("implement", "repair", status_is("failed"), 2),
            ("implement", "verify", status_is("succeeded"), None),
            ("verify", "deliver", status_is("passed"), None),
            ("repair", "verify", None, None),
        ],
    )
    executor = FakeExecutor(
        {
            "implement": [executor_result(ExecutorStatus.FAILED)],
            "repair": [executor_result(ExecutorStatus.SUCCEEDED)],
            "deliver": [executor_result(ExecutorStatus.SUCCEEDED)],
        }
    )
    verifier = FakeVerifier({"verify": [verifier_result(VerifierStatus.PASSED)]})
    runtime = GraphRuntime(tmp_path, executor=executor, verifier=verifier)
    runtime.create_run("run-1", "project-1", definition, CONTRACT_HASH, budget())

    assert runtime.run("run-1") is TerminalStatus.SUCCEEDED
    assert [call.node_id for call in executor.calls] == ["implement", "repair", "deliver"]
    assert runtime.snapshot("run-1").budget_usage.repair_iterations == 1


def test_verifier_failed_and_error_take_different_routes(tmp_path: Path) -> None:
    definition = graph(
        [
            ("verify", NodeType.VERIFIER, None),
            ("repair", NodeType.AGENT, None),
            ("infra_stop", NodeType.DELIVERY, None),
        ],
        [
            ("verify", "repair", status_is("failed"), 1),
            ("verify", "infra_stop", status_is("error"), None),
        ],
    )
    failed_runtime = GraphRuntime(
        tmp_path / "failed",
        executor=FakeExecutor({"repair": [executor_result(ExecutorStatus.SUCCEEDED)]}),
        verifier=FakeVerifier({"verify": [verifier_result(VerifierStatus.FAILED)]}),
    )
    failed_runtime.create_run("run-f", "project", definition, CONTRACT_HASH, budget())
    failed_runtime.run("run-f")
    assert "repair" in failed_runtime.snapshot("run-f").started_node_ids

    error_runtime = GraphRuntime(
        tmp_path / "error",
        executor=FakeExecutor({"infra_stop": [executor_result(ExecutorStatus.SUCCEEDED)]}),
        verifier=FakeVerifier({"verify": [verifier_result(VerifierStatus.ERROR)]}),
    )
    error_runtime.create_run("run-e", "project", definition, CONTRACT_HASH, budget())
    error_runtime.run("run-e")
    assert "infra_stop" in error_runtime.snapshot("run-e").started_node_ids
    assert "repair" not in error_runtime.snapshot("run-e").started_node_ids


def test_budget_exhaustion_and_cancel_create_reports(tmp_path: Path) -> None:
    definition = graph(
        [("one", NodeType.AGENT, None), ("two", NodeType.AGENT, None)],
        [("one", "two", None, None)],
    )
    runtime = GraphRuntime(
        tmp_path / "budget",
        executor=FakeExecutor(
            {
                "one": [executor_result(ExecutorStatus.SUCCEEDED)],
                "two": [executor_result(ExecutorStatus.SUCCEEDED)],
            }
        ),
        verifier=FakeVerifier(),
    )
    runtime.create_run("run-b", "project", definition, CONTRACT_HASH, budget(calls=1))
    assert runtime.run("run-b") is TerminalStatus.FAILED
    assert runtime.final_report("run-b").terminal_reason is TerminalReason.BUDGET_EXHAUSTED

    cancelled = GraphRuntime(tmp_path / "cancel", executor=FakeExecutor(), verifier=FakeVerifier())
    cancelled.create_run("run-c", "project", definition, CONTRACT_HASH, budget())
    cancelled.cancel("run-c")
    assert cancelled.final_report("run-c").terminal_status is TerminalStatus.CANCELLED


def test_error_terminal_report_is_distinct_from_failed(tmp_path: Path) -> None:
    definition = graph([("implement", NodeType.AGENT, None)], [])
    runtime = GraphRuntime(
        tmp_path,
        executor=FakeExecutor({"implement": [executor_result(ExecutorStatus.ERROR)]}),
        verifier=FakeVerifier(),
    )
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())

    assert runtime.run("run-1") is TerminalStatus.ERROR
    report = runtime.final_report("run-1")
    assert report.terminal_status is TerminalStatus.ERROR
    assert report.error is not None
