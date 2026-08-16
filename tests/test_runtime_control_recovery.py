from __future__ import annotations

from pathlib import Path

import pytest
from runtime_helpers import budget, graph

from graph_engineering.models import (
    ControlReason,
    ExecutorResult,
    QueryControlIntent,
    RestartFrom,
    RunRelationship,
    StateChangeControlIntent,
    VerifierResult,
)
from graph_engineering.models.common import RestartStrategy
from graph_engineering.models.control import (
    ControlReasonCode,
    QueryAction,
    StateChangeAction,
    Urgency,
)
from graph_engineering.models.graph import NodeType
from graph_engineering.models.reports import TerminalStatus
from graph_engineering.models.results import ExecutorStatus, VerifierStatus
from graph_engineering.runtime import FakeExecutor, FakeVerifier, GraphRuntime, RecoveryError

CONTRACT_HASH = "b" * 64


def succeeded() -> ExecutorResult:
    return ExecutorResult(schema_version="1.0", status=ExecutorStatus.SUCCEEDED, summary="done")


def intent(run_id: str, action: StateChangeAction, intent_id: str) -> StateChangeControlIntent:
    return StateChangeControlIntent(
        schema_version="1.0",
        intent_kind="state_change",
        intent_id=intent_id,
        source_message_id=f"message-{intent_id}",
        actor_id="human",
        project_id="project",
        run_id=run_id,
        action=action,
        reason=ControlReason(schema_version="1.0", code=ControlReasonCode.HUMAN_REQUEST),
        urgency=Urgency.IMMEDIATE,
        confidence=1,
        requires_confirmation=False,
    )


def query(run_id: str, intent_id: str) -> QueryControlIntent:
    return QueryControlIntent(
        schema_version="1.0",
        intent_kind="query",
        intent_id=intent_id,
        source_message_id=f"message-{intent_id}",
        actor_id="human",
        project_id="project",
        run_id=run_id,
        action=QueryAction.QUERY_PROGRESS,
        reason=ControlReason(schema_version="1.0", code=ControlReasonCode.RISK_REVIEW),
        confidence=1,
    )


def test_checkpoint_recovery_does_not_repeat_completed_nodes(tmp_path: Path) -> None:
    definition = graph(
        [("one", NodeType.AGENT, None), ("two", NodeType.AGENT, None)],
        [("one", "two", None, None)],
    )
    first = FakeExecutor({"one": [succeeded()], "two": [succeeded()]})
    runtime = GraphRuntime(tmp_path, executor=first, verifier=FakeVerifier())
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())
    runtime.run("run-1", max_steps=1)
    assert [call.node_id for call in first.calls] == ["one"]

    resumed_executor = FakeExecutor({"two": [succeeded()]})
    resumed = GraphRuntime(tmp_path, executor=resumed_executor, verifier=FakeVerifier())
    resumed.recover("run-1", definition, CONTRACT_HASH)
    assert resumed.run("run-1") is TerminalStatus.SUCCEEDED
    assert [call.node_id for call in resumed_executor.calls] == ["two"]


def test_recovery_rejects_contract_or_graph_hash_mismatch(tmp_path: Path) -> None:
    definition = graph([("one", NodeType.AGENT, None)], [])
    runtime = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())

    with pytest.raises(RecoveryError, match="Contract hash"):
        runtime.recover("run-1", definition, "c" * 64)
    changed = graph([("different", NodeType.AGENT, None)], [], graph_id="graph-2")
    with pytest.raises(RecoveryError, match="Graph hash"):
        runtime.recover("run-1", changed, CONTRACT_HASH)


def test_repeated_queries_do_not_change_execution_state_or_context(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace.txt"
    workspace.write_text("unchanged", encoding="utf-8")
    definition = graph([("one", NodeType.AGENT, None)], [])
    executor = FakeExecutor({"one": [succeeded()]})
    runtime = GraphRuntime(tmp_path / "run", executor=executor, verifier=FakeVerifier())
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())
    before = runtime.snapshot("run-1").execution_fingerprint()

    for number in range(5):
        result = runtime.control(query("run-1", f"q-{number}"))
        assert result.state_changed is False
        runtime.live_report("run-1")

    assert runtime.snapshot("run-1").execution_fingerprint() == before
    assert executor.calls == []
    assert workspace.read_text(encoding="utf-8") == "unchanged"


def test_pause_and_interrupt_barriers_prevent_new_attempts(tmp_path: Path) -> None:
    definition = graph(
        [("one", NodeType.AGENT, None), ("two", NodeType.AGENT, None)],
        [("one", "two", None, None)],
    )
    executor = FakeExecutor({"one": [succeeded()], "two": [succeeded()]})
    runtime = GraphRuntime(tmp_path / "pause", executor=executor, verifier=FakeVerifier())
    runtime.create_run("run-p", "project", definition, CONTRACT_HASH, budget())
    executor.after_execute = lambda _: runtime.control(
        intent("run-p", StateChangeAction.PAUSE, "pause-1")
    )
    assert runtime.run("run-p") == "paused"
    assert [call.node_id for call in executor.calls] == ["one"]
    runtime.control(intent("run-p", StateChangeAction.RESUME, "resume-1"))
    executor.after_execute = None
    assert runtime.run("run-p") is TerminalStatus.SUCCEEDED

    interrupt_executor = FakeExecutor({"one": [succeeded()], "two": [succeeded()]})
    interrupted = GraphRuntime(
        tmp_path / "interrupt", executor=interrupt_executor, verifier=FakeVerifier()
    )
    interrupted.create_run("run-i", "project", definition, CONTRACT_HASH, budget())
    interrupt_executor.after_execute = lambda _: interrupted.control(
        intent("run-i", StateChangeAction.INTERRUPT, "interrupt-1")
    )
    assert interrupted.run("run-i") is TerminalStatus.INTERRUPTED
    assert [call.node_id for call in interrupt_executor.calls] == ["one"]
    assert interrupted.final_report("run-i").terminal_status is TerminalStatus.INTERRUPTED


def test_persisted_pause_barrier_prevents_an_external_trigger(tmp_path: Path) -> None:
    definition = graph(
        [("one", NodeType.AGENT, None), ("ci", NodeType.VERIFIER, {"external": True})],
        [("one", "ci", None, None)],
    )
    executor = FakeExecutor({"one": [succeeded()]})
    verifier = FakeVerifier()
    runtime = GraphRuntime(tmp_path, executor=executor, verifier=verifier)
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())
    executor.after_execute = lambda _: runtime.control(
        intent("run-1", StateChangeAction.PAUSE, "pause-before-ci")
    )

    assert runtime.run("run-1") == "paused"
    assert verifier.trigger_count == 0
    assert runtime.snapshot("run-1").budget_usage.executor_calls == 1


def test_external_handle_is_queried_not_retriggered_after_recovery(tmp_path: Path) -> None:
    definition = graph([("ci", NodeType.VERIFIER, {"external": True})], [])
    verifier = FakeVerifier(
        {
            "ci": [
                VerifierResult(
                    schema_version="1.0",
                    status=VerifierStatus.PENDING,
                    summary="started",
                    external_handle="ci-123",
                )
            ]
        },
        query_results={
            "ci-123": [
                VerifierResult(schema_version="1.0", status=VerifierStatus.PASSED, summary="passed")
            ]
        },
    )
    runtime = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=verifier)
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())
    runtime.run("run-1", max_steps=1)
    assert verifier.trigger_count == 1

    resumed = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=verifier)
    resumed.recover("run-1", definition, CONTRACT_HASH)
    assert resumed.run("run-1") is TerminalStatus.SUCCEEDED
    assert verifier.trigger_count == 1
    assert verifier.query_count == 1


def test_uncertain_external_trigger_stops_and_is_disclosed(tmp_path: Path) -> None:
    definition = graph([("ci", NodeType.VERIFIER, {"external": True})], [])
    runtime = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())
    with runtime.state.transaction() as connection:
        connection.execute(
            "UPDATE nodes SET status = 'running', attempt_count = 1 WHERE run_id = 'run-1' "
            "AND node_id = 'ci'"
        )
        connection.execute(
            "INSERT INTO attempts(attempt_id, run_id, node_id, attempt_number, status, started_at) "
            "VALUES ('run-1:ci:1', 'run-1', 'ci', 1, 'running', '2026-08-16T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO external_handles("
            "run_id, node_id, idempotency_key, trigger_state, updated_at"
            ") VALUES ("
            "'run-1', 'ci', 'run-1:ci', 'triggering', '2026-08-16T00:00:00Z'"
            ")"
        )

    recovered = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=FakeVerifier())
    recovered.recover("run-1", definition, CONTRACT_HASH)
    report = recovered.final_report("run-1")
    assert report.terminal_status is TerminalStatus.ERROR
    assert report.unverified_items
    assert report.external_effects[0].reversible is False


def test_invalid_state_transition_is_rejected_without_mutation(tmp_path: Path) -> None:
    definition = graph([("one", NodeType.AGENT, None)], [])
    runtime = GraphRuntime(
        tmp_path, executor=FakeExecutor({"one": [succeeded()]}), verifier=FakeVerifier()
    )
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())
    assert runtime.run("run-1") is TerminalStatus.SUCCEEDED
    before = runtime.snapshot("run-1").execution_fingerprint()

    result = runtime.control(intent("run-1", StateChangeAction.PAUSE, "late-pause"))

    assert result.state_changed is False
    assert result.outcome == "rejected"
    assert runtime.snapshot("run-1").execution_fingerprint() == before


def test_run_relationship_and_restart_root_are_persisted(tmp_path: Path) -> None:
    definition = graph([("one", NodeType.AGENT, None)], [])
    runtime = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.create_run("run-old", "project", definition, CONTRACT_HASH, budget())
    checkpoint = runtime.latest_checkpoint("run-old")
    relationship = RunRelationship(
        schema_version="1.0",
        run_id="run-new",
        parent_run_id="run-old",
        supersedes_run_id="run-old",
    )
    restart = RestartFrom(
        schema_version="1.0", strategy=RestartStrategy.CHECKPOINT, reference=checkpoint
    )
    runtime.create_run(
        "run-new", "project", definition, CONTRACT_HASH, budget(), relationship, restart
    )

    snapshot = runtime.snapshot("run-new")
    assert snapshot.relationship == relationship
    assert snapshot.restart_from == restart


def test_checkpoint_restart_inherits_completed_state_without_mutating_parent(
    tmp_path: Path,
) -> None:
    definition = graph(
        [("one", NodeType.AGENT, None), ("two", NodeType.AGENT, None)],
        [("one", "two", None, None)],
    )
    parent_executor = FakeExecutor({"one": [succeeded()]})
    runtime = GraphRuntime(tmp_path, executor=parent_executor, verifier=FakeVerifier())
    runtime.create_run("run-old", "project", definition, CONTRACT_HASH, budget())
    runtime.run("run-old", max_steps=1)
    checkpoint = runtime.latest_checkpoint("run-old")
    parent_before = runtime.snapshot("run-old").execution_fingerprint()

    child_executor = FakeExecutor({"two": [succeeded()]})
    child_runtime = GraphRuntime(tmp_path, executor=child_executor, verifier=FakeVerifier())
    child_runtime.create_run(
        "run-new",
        "project",
        definition,
        CONTRACT_HASH,
        budget(),
        RunRelationship(
            schema_version="1.0",
            run_id="run-new",
            parent_run_id="run-old",
            supersedes_run_id="run-old",
        ),
        RestartFrom(
            schema_version="1.0",
            strategy=RestartStrategy.CHECKPOINT,
            reference=checkpoint,
        ),
    )

    assert child_runtime.run("run-new") is TerminalStatus.SUCCEEDED
    assert [call.node_id for call in child_executor.calls] == ["two"]
    assert child_runtime.snapshot("run-old").execution_fingerprint() == parent_before


def test_run_relationship_and_checkpoint_references_are_validated(tmp_path: Path) -> None:
    definition = graph([("one", NodeType.AGENT, None)], [])
    runtime = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=FakeVerifier())
    missing_parent = RunRelationship(
        schema_version="1.0", run_id="run-new", parent_run_id="missing"
    )

    with pytest.raises(ValueError, match="parent Run"):
        runtime.create_run(
            "run-new",
            "project",
            definition,
            CONTRACT_HASH,
            budget(),
            missing_parent,
            RestartFrom(schema_version="1.0", strategy=RestartStrategy.CLEAN_BASE),
        )

    runtime.create_run("run-old", "project", definition, CONTRACT_HASH, budget())
    relationship = RunRelationship(schema_version="1.0", run_id="run-new", parent_run_id="run-old")
    with pytest.raises(ValueError, match="checkpoint"):
        runtime.create_run(
            "run-new",
            "project",
            definition,
            CONTRACT_HASH,
            budget(),
            relationship,
            RestartFrom(
                schema_version="1.0",
                strategy=RestartStrategy.CHECKPOINT,
                reference="checkpoint:missing",
            ),
        )
