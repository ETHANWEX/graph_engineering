from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from runtime_helpers import budget, graph

from graph_engineering.models import Budget, ExecutorResult, VerifierResult
from graph_engineering.models.common import ArtifactKind
from graph_engineering.models.graph import NodeType
from graph_engineering.models.reports import TerminalReason, TerminalStatus
from graph_engineering.models.results import ExecutorStatus, VerifierStatus
from graph_engineering.runtime import FakeExecutor, FakeVerifier, GraphRuntime

CONTRACT_HASH = "d" * 64


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 16, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def succeeded(*, changed_files: list[str] | None = None) -> ExecutorResult:
    return ExecutorResult(
        schema_version="1.0",
        status=ExecutorStatus.SUCCEEDED,
        summary="done",
        changed_files=changed_files or [],
    )


def failed() -> ExecutorResult:
    return ExecutorResult(
        schema_version="1.0",
        status=ExecutorStatus.FAILED,
        summary="failed",
        failure_reason="failed",
    )


def test_duration_budget_stops_before_a_new_attempt(tmp_path: Path) -> None:
    clock = MutableClock()
    definition = graph(
        [("one", NodeType.AGENT, None), ("two", NodeType.AGENT, None)],
        [("one", "two", None, None)],
    )
    executor = FakeExecutor({"one": [succeeded()], "two": [succeeded()]})
    runtime = GraphRuntime(tmp_path, executor=executor, verifier=FakeVerifier(), clock=clock)
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget(duration=10))
    executor.after_execute = lambda _: clock.advance(11)

    assert runtime.run("run-1") is TerminalStatus.FAILED
    assert [call.node_id for call in executor.calls] == ["one"]
    assert runtime.final_report("run-1").terminal_reason is TerminalReason.BUDGET_EXHAUSTED


def test_node_call_budget_is_enforced_across_a_repair_loop(tmp_path: Path) -> None:
    node_budget = Budget(
        schema_version="1.0",
        max_duration_seconds=3600,
        max_executor_calls=1,
        max_repair_iterations=5,
    )
    definition = graph(
        [
            ("implement", NodeType.AGENT, {"marker": "node-budget"}),
            ("repair", NodeType.AGENT, None),
        ],
        [
            ("implement", "repair", None, None),
            ("repair", "implement", None, None),
        ],
    )
    definition = definition.model_copy(
        update={
            "nodes": [
                definition.nodes[0].model_copy(update={"budget": node_budget}),
                definition.nodes[1],
            ]
        }
    )
    executor = FakeExecutor({"implement": [failed(), succeeded()], "repair": [succeeded()]})
    runtime = GraphRuntime(tmp_path, executor=executor, verifier=FakeVerifier())
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())

    assert runtime.run("run-1") is TerminalStatus.FAILED
    assert [call.node_id for call in executor.calls] == ["implement", "repair"]
    assert runtime.final_report("run-1").terminal_reason is TerminalReason.BUDGET_EXHAUSTED


def test_node_duration_and_repair_budgets_are_enforced(tmp_path: Path) -> None:
    clock = MutableClock()
    duration_definition = graph([("one", NodeType.AGENT, None)], [])
    duration_definition = duration_definition.model_copy(
        update={
            "nodes": [
                duration_definition.nodes[0].model_copy(update={"budget": budget(duration=5)})
            ]
        }
    )
    duration_executor = FakeExecutor({"one": [succeeded()]})
    duration_runtime = GraphRuntime(
        tmp_path / "duration",
        executor=duration_executor,
        verifier=FakeVerifier(),
        clock=clock,
    )
    duration_runtime.create_run(
        "run-duration", "project", duration_definition, CONTRACT_HASH, budget(duration=100)
    )
    duration_executor.after_execute = lambda _: clock.advance(6)
    assert duration_runtime.run("run-duration") is TerminalStatus.FAILED

    repair_definition = graph(
        [("implement", NodeType.AGENT, None), ("repair", NodeType.AGENT, None)],
        [("implement", "repair", None, 5)],
    )
    repair_definition = repair_definition.model_copy(
        update={
            "nodes": [
                repair_definition.nodes[0].model_copy(update={"budget": budget(repairs=0)}),
                repair_definition.nodes[1],
            ]
        }
    )
    repair_executor = FakeExecutor({"implement": [failed()], "repair": [succeeded()]})
    repair_runtime = GraphRuntime(
        tmp_path / "repair", executor=repair_executor, verifier=FakeVerifier()
    )
    repair_runtime.create_run("run-repair", "project", repair_definition, CONTRACT_HASH, budget())
    assert repair_runtime.run("run-repair") is TerminalStatus.FAILED
    assert [call.node_id for call in repair_executor.calls] == ["implement"]


def test_explicit_cost_charge_enforces_run_and_node_budgets(tmp_path: Path) -> None:
    definition = graph([("one", NodeType.AGENT, None)], [])
    definition = definition.model_copy(
        update={
            "nodes": [definition.nodes[0].model_copy(update={"budget": budget(cost=2, calls=2)})]
        }
    )
    runtime = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget(cost=10))

    runtime.charge_cost("run-1", 3, node_id="one")

    assert runtime.final_report("run-1").terminal_reason is TerminalReason.BUDGET_EXHAUSTED
    assert runtime.snapshot("run-1").budget_usage.cost_units == 3


def test_artifact_metadata_and_result_evidence_are_aggregated(tmp_path: Path) -> None:
    definition = graph(
        [("implement", NodeType.AGENT, None), ("verify", NodeType.VERIFIER, None)],
        [("implement", "verify", None, None)],
    )
    runtime = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())
    implementation_artifact = runtime.store_artifact(
        "run-1", b"implementation log", media_type="text/plain", kind=ArtifactKind.LOG
    )
    verification_artifact = runtime.artifacts.put_bytes(
        b"verification evidence", media_type="application/json", kind=ArtifactKind.TEST_RESULT
    )
    runtime.executor = FakeExecutor(
        {
            "implement": [
                succeeded(changed_files=["src/example.py"]).model_copy(
                    update={"artifacts": [implementation_artifact]}
                )
            ]
        }
    )
    runtime.verifier = FakeVerifier(
        {
            "verify": [
                VerifierResult(
                    schema_version="1.0",
                    status=VerifierStatus.PASSED,
                    summary="passed",
                    artifacts=[verification_artifact],
                )
            ]
        }
    )
    assert runtime.run("run-1") is TerminalStatus.SUCCEEDED
    report = runtime.final_report("run-1")
    assert report.changed_files == ["src/example.py"]
    assert report.verification_artifacts == [verification_artifact]
    with runtime.state.read_connection() as connection:
        metadata_count = connection.execute("SELECT COUNT(*) FROM artifact_metadata").fetchone()[0]
        links = connection.execute("SELECT COUNT(*) FROM run_artifacts").fetchone()[0]
    assert metadata_count == 2
    assert links == 3  # runtime registration plus executor/verifier evidence roles
    event_types = {
        json.loads(line)["event_type"]
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    }
    assert "artifact.created" in event_types
