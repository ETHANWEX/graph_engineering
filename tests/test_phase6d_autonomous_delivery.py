import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from graph_engineering.cli import app
from graph_engineering.contracts import ContractRepository, RunPlanner
from graph_engineering.delivery import (
    AutonomousDeliveryCoordinator,
    ReviewAggregate,
    ReviewDimension,
    ReviewDimensionResult,
    ReviewFinding,
    ReviewStatus,
    ReviewVerdict,
    RunStartError,
    RunStartUncertainError,
)
from graph_engineering.mcp_server import TOOLS, MCPServer
from graph_engineering.models import Error, HumanMessage
from graph_engineering.models.common import ErrorKind
from graph_engineering.models.results import (
    ExecutorResult,
    ExecutorStatus,
    VerifierResult,
    VerifierStatus,
)
from graph_engineering.runtime import FakeExecutor, FakeVerifier, StateStore
from graph_engineering.service.protocol import IPCRequest


def _message(message_id: str = "confirm-1") -> HumanMessage:
    return HumanMessage(
        schema_version="1.0",
        message_id=message_id,
        actor_id="human",
        project_id="project",
        content="I explicitly confirm this Contract",
        created_at=datetime(2026, 8, 25, tzinfo=UTC),
    )


def _prepared(root: Path) -> str:
    state = StateStore(root / ".ge" / "control" / "phase3.db")
    contracts = ContractRepository(state)
    draft = contracts.example_draft("contract-1", "Implement greeting", "python -m pytest")
    frozen = contracts.freeze(contracts.stage("conversation-1", draft), _message())
    return RunPlanner(state).create("project", frozen, run_id="run-1").run_id


def _success() -> ExecutorResult:
    return ExecutorResult(schema_version="1.0", status=ExecutorStatus.SUCCEEDED, summary="ok")


def test_explicit_start_is_idempotent_and_confirmation_has_no_effect(tmp_path: Path) -> None:
    run_id = _prepared(tmp_path)
    control = StateStore(tmp_path / ".ge" / "control" / "phase3.db")
    with control.read_connection() as connection:
        assert connection.execute("SELECT status FROM planned_runs").fetchone()[0] == "prepared"
        assert connection.execute("SELECT COUNT(*) FROM executor_sessions").fetchone()[0] == 0
    executor = FakeExecutor(
        {name: [_success()] for name in ("inspect", "implement", "review", "deliver")}
    )
    verifier = FakeVerifier(
        {
            "verify.project-tests": [
                VerifierResult(schema_version="1.0", status=VerifierStatus.PASSED, summary="passed")
            ]
        }
    )
    coordinator = AutonomousDeliveryCoordinator(tmp_path, executor=executor, verifier=verifier)
    first = coordinator.run(run_id, request_id="request-1", idempotency_key="start-1")
    replay = coordinator.run(run_id, request_id="request-2", idempotency_key="start-1")
    assert first == replay
    assert first.runtime_status == "succeeded"
    assert [call.node_id for call in executor.calls] == [
        "inspect",
        "implement",
        "review",
        "deliver",
    ]
    assert len(verifier.calls) == 1
    assert coordinator.report(run_id).revision == 1


def test_claimed_unknown_start_fails_closed_without_executor_call(tmp_path: Path) -> None:
    run_id = _prepared(tmp_path)
    coordinator = AutonomousDeliveryCoordinator(
        tmp_path, executor=FakeExecutor(), verifier=FakeVerifier()
    )
    coordinator.claim_start_for_test(run_id, "uncertain-key")
    with pytest.raises(RunStartUncertainError):
        coordinator.run(run_id, request_id="request-2", idempotency_key="uncertain-key")
    with pytest.raises(RunStartUncertainError):
        coordinator.run(run_id, request_id="request-3", idempotency_key="different-key")


def test_frozen_graph_drift_is_rejected_before_any_side_effect(tmp_path: Path) -> None:
    run_id = _prepared(tmp_path)
    control = StateStore(tmp_path / ".ge" / "control" / "phase3.db")
    with control.transaction() as connection:
        connection.execute(
            "UPDATE planned_runs SET graph_hash=? WHERE run_id=?", ("f" * 64, run_id)
        )
    executor = FakeExecutor()
    coordinator = AutonomousDeliveryCoordinator(
        tmp_path, executor=executor, verifier=FakeVerifier()
    )
    with pytest.raises(RunStartError, match="drift"):
        coordinator.run(run_id, request_id="drift", idempotency_key="drift")
    assert executor.calls == []


def test_verifier_infrastructure_error_never_enters_repair(tmp_path: Path) -> None:
    run_id = _prepared(tmp_path)
    executor = FakeExecutor({name: [_success()] for name in ("inspect", "implement")})
    verifier = FakeVerifier(
        {
            "verify.project-tests": [
                VerifierResult(
                    schema_version="1.0",
                    status=VerifierStatus.ERROR,
                    summary="container runtime unavailable",
                    error=Error(
                        schema_version="1.0",
                        kind=ErrorKind.INFRASTRUCTURE,
                        code="container.runtime_unavailable",
                        message="container runtime unavailable",
                        retryable=False,
                    ),
                )
            ]
        }
    )
    result = AutonomousDeliveryCoordinator(tmp_path, executor=executor, verifier=verifier).run(
        run_id, request_id="infra", idempotency_key="infra"
    )
    assert result.runtime_status == "error"
    assert [call.node_id for call in executor.calls] == ["inspect", "implement"]


def test_verifier_and_review_changes_use_bounded_fresh_repair_loops(tmp_path: Path) -> None:
    run_id = _prepared(tmp_path)
    executor = FakeExecutor(
        {name: [_success()] for name in ("inspect", "implement", "repair", "review_fix", "deliver")}
    )
    failed = VerifierResult(
        schema_version="1.0",
        status=VerifierStatus.FAILED,
        summary="acceptance failed",
        failure_details=["expected greeting"],
    )
    passed = VerifierResult(schema_version="1.0", status=VerifierStatus.PASSED, summary="passed")
    verifier = FakeVerifier({"verify.project-tests": [failed, passed, passed]})
    review_calls = 0

    def reviewer(_run_id: str, _attempt_id: str) -> ReviewAggregate:
        nonlocal review_calls
        review_calls += 1
        verdict = ReviewVerdict.CHANGES_REQUESTED if review_calls == 1 else ReviewVerdict.APPROVED
        results = []
        for dimension in ReviewDimension:
            findings: tuple[ReviewFinding, ...] = ()
            item_verdict = (
                verdict if dimension is ReviewDimension.CORRECTNESS else ReviewVerdict.APPROVED
            )
            if item_verdict is ReviewVerdict.CHANGES_REQUESTED:
                findings = (
                    ReviewFinding(
                        severity="high",
                        category="correctness",
                        file="app.py",
                        impact="wrong boundary",
                        required_change="fix greeting",
                        contract_refs=("requested-behavior",),
                    ),
                )
            results.append(
                ReviewDimensionResult(
                    dimension=dimension,
                    status=ReviewStatus.COMPLETED,
                    verdict=item_verdict,
                    summary=item_verdict.value,
                    findings=findings,
                    session_id=f"fresh-{review_calls}-{dimension.value}",
                    sandbox="read-only",
                )
            )
        all_findings = tuple(finding for item in results for finding in item.findings)
        return ReviewAggregate(
            verdict=verdict, dimension_results=tuple(results), findings=all_findings
        )

    result = AutonomousDeliveryCoordinator(
        tmp_path, executor=executor, verifier=verifier, reviewer=reviewer
    ).run(run_id, request_id="loop-request", idempotency_key="loop-start")
    assert result.runtime_status == "succeeded"
    assert [call.node_id for call in executor.calls] == [
        "inspect",
        "implement",
        "repair",
        "review_fix",
        "deliver",
    ]
    assert review_calls == 2
    with StateStore(
        tmp_path / ".ge" / "runs" / run_id / "state.db"
    ).read_connection() as connection:
        classifications = [
            row[0]
            for row in connection.execute(
                "SELECT classification FROM delivery_stage_checkpoints ORDER BY created_at"
            )
        ]
    assert classifications == ["review_changes_requested", "review_approved"]


def test_revise_creates_prepared_successor_and_new_explicit_start_lineage(tmp_path: Path) -> None:
    run_id = _prepared(tmp_path)
    executor = FakeExecutor(
        {name: [_success()] for name in ("inspect", "implement", "review", "deliver")}
    )
    verifier = FakeVerifier(
        {
            "verify.project-tests": [
                VerifierResult(schema_version="1.0", status=VerifierStatus.PASSED, summary="passed")
            ]
        }
    )
    coordinator = AutonomousDeliveryCoordinator(tmp_path, executor=executor, verifier=verifier)
    coordinator.run(run_id, request_id="start", idempotency_key="start")
    revision_message = HumanMessage(
        schema_version="1.0",
        message_id="revise-message",
        actor_id="human",
        project_id="project",
        run_id=run_id,
        content=f"confirm revise {run_id}: use a revised greeting",
        created_at=datetime(2026, 8, 25, tzinfo=UTC),
    )
    record = coordinator.decide(
        "revise", revision_message, reason="use a revised greeting", report_revision=1
    )
    assert record.new_contract_revision == 2 and record.new_run_id
    assert ":" not in record.new_run_id
    with StateStore(tmp_path / ".ge" / "control" / "phase3.db").read_connection() as connection:
        successor = connection.execute(
            "SELECT status,parent_run_id,supersedes_run_id FROM planned_runs WHERE run_id=?",
            (record.new_run_id,),
        ).fetchone()
        old_hash = connection.execute(
            "SELECT contract_hash FROM contract_revisions "
            "WHERE contract_id='contract-1' AND revision=1"
        ).fetchone()[0]
    assert tuple(successor) == ("prepared", run_id, run_id)
    assert old_hash
    assert coordinator.report(run_id).revision == 2


def test_phase6d_cli_and_mcp_surface_is_complete_and_strict() -> None:
    help_result = CliRunner().invoke(app, ["--help"])
    assert help_result.exit_code == 0
    for command in (
        "run",
        "status",
        "pause",
        "resume",
        "interrupt",
        "cancel",
        "report",
        "accept",
        "reject",
        "revise",
    ):
        assert command in help_result.output
    tool_names = {item["name"] for item in TOOLS}
    assert {
        "run",
        "status",
        "pause",
        "resume",
        "interrupt",
        "cancel",
        "report",
        "accept",
        "reject",
        "revise",
    } <= tool_names
    run_schema = next(item["inputSchema"] for item in TOOLS if item["name"] == "run")
    assert run_schema["additionalProperties"] is False
    assert "shell" not in run_schema["properties"]


def test_phase6d_mcp_and_ipc_fixtures_route_without_unknown_field_bypass(tmp_path: Path) -> None:
    class FixtureClient:
        def call(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
            return {"operation": operation, "run_id": payload["run_id"]}

    server = MCPServer(tmp_path)
    server.client = cast(Any, FixtureClient())
    request = json.loads(Path("tests/fixtures/phase6d/mcp-run-call.json").read_text())
    response = server.handle(request)
    assert response is not None
    content = json.loads(response["result"]["content"][0]["text"])
    assert content == {"operation": "run", "run_id": "run-fixture"}
    request["params"]["arguments"]["shell"] = "echo forbidden"
    rejected = server.handle(request)
    assert rejected is not None and rejected["error"]["code"] == -32602

    ipc = json.loads(Path("tests/fixtures/phase6d/ipc-pause-request.json").read_text())
    assert IPCRequest.model_validate(ipc).operation == "pause"


def test_migration_10_is_repeatable_and_preserves_phase6c_view(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    state.migrate()
    assert state.autonomous_delivery_migration_version == 10
    assert state.container_migration_version == 9
    with state.read_connection() as connection:
        assert [
            row[0] for row in connection.execute("SELECT version FROM schema_migrations")
        ] == list(range(1, 11))


def test_product_cli_deterministic_git_fixture_from_discovery_to_bundle(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=tmp_path, check=True)
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True)

    runner = CliRunner()

    def start(text: str) -> Any:
        return runner.invoke(
            app,
            [
                "start",
                "--project-root",
                str(tmp_path),
                "--conversation-id",
                "conversation-1",
                "--message",
                text,
            ],
        )

    assert start("Add a greeting endpoint").exit_code == 0
    for answer in (
        "python -m pytest",
        "GET /greeting returns hello",
        "No interface changes",
        "Follow existing Python style",
        "No network or secrets",
        "report only",
        "one hour and 20 calls",
    ):
        assert start(answer).exit_code == 0
    confirmed = start("I explicitly confirm this Contract")
    assert confirmed.exit_code == 0 and "has not started" in confirmed.output
    with sqlite3.connect(tmp_path / ".ge" / "control" / "phase3.db") as connection:
        run_id = str(connection.execute("SELECT run_id FROM planned_runs").fetchone()[0])
    executed = runner.invoke(
        app,
        [
            "run",
            run_id,
            "--project-root",
            str(tmp_path),
            "--deterministic-fixture",
            "--request-id",
            "request-e2e",
            "--idempotency-key",
            "start-e2e",
        ],
    )
    assert executed.exit_code == 0, executed.output
    report = runner.invoke(
        app, ["report", run_id, "--state-db", str(tmp_path / ".ge" / "runs" / run_id / "state.db")]
    )
    assert report.exit_code == 0
    assert len(__import__("json").loads(report.output)["files"]) == 10
