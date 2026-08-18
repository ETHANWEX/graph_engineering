# ruff: noqa: E501

from datetime import UTC, datetime
from pathlib import Path

import pytest

from graph_engineering.delivery import DeliveryReportCompiler, HumanDecisionService
from graph_engineering.models import HumanMessage
from graph_engineering.runtime import ArtifactStore, StateStore


@pytest.mark.parametrize(
    "terminal", ["succeeded", "failed", "interrupted", "cancelled", "rejected"]
)
def test_every_terminal_compiles_versioned_delivery_bundle(tmp_path: Path, terminal: str) -> None:
    state = StateStore(tmp_path / terminal / "state.db")
    state.migrate()
    # A minimal persisted terminal fixture proves compilation does not need an Agent Session.
    with state.transaction() as connection:
        connection.execute(
            "INSERT INTO delivery_terminal_fixtures(run_id, contract_id, contract_revision, status, reason, created_at) VALUES (?, ?, 1, ?, ?, ?)",
            (
                f"run-{terminal}",
                "contract-1",
                terminal,
                f"reason:{terminal}",
                datetime.now(UTC).isoformat(),
            ),
        )
    compiler = DeliveryReportCompiler(
        state, ArtifactStore(tmp_path / terminal / "artifacts"), tmp_path / terminal / "reports"
    )
    bundle = compiler.compile(f"run-{terminal}")
    assert bundle.terminal_status == terminal
    assert set(bundle.files) == {
        "summary.md",
        "requirement-matrix.md",
        "changes.diff",
        "test-results.json",
        "review-report.md",
        "execution-trace.json",
        "cost-report.json",
        "pull-request.json",
        "control-history.json",
        "external-effects.json",
    }
    second = compiler.compile(f"run-{terminal}")
    assert second.revision == bundle.revision + 1
    assert (tmp_path / terminal / "reports" / f"run-{terminal}" / "1" / "summary.md").exists()


def message(message_id: str, content: str, run_id: str) -> HumanMessage:
    return HumanMessage(
        schema_version="1.0",
        message_id=message_id,
        actor_id="human",
        project_id="project",
        run_id=run_id,
        content=content,
        created_at=datetime.now(UTC),
    )


def test_accept_is_idempotent_never_merges_and_reject_requires_reason(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    with state.transaction() as connection:
        connection.execute(
            "INSERT INTO delivery_terminal_fixtures(run_id, contract_id, contract_revision, status, reason, created_at) VALUES ('run-1', 'contract-1', 1, 'succeeded', 'completed', ?)",
            (datetime.now(UTC).isoformat(),),
        )
    service = HumanDecisionService(state)
    accepted = service.accept(message("m1", "confirm accept run-1", "run-1"), report_revision=1)
    assert accepted.action == "accept"
    assert accepted.merge_performed is False
    assert (
        service.accept(message("m1", "confirm accept run-1", "run-1"), report_revision=1)
        == accepted
    )
    with pytest.raises(ValueError, match="reason"):
        service.reject(message("m2", "confirm reject run-1", "run-1"), reason="", report_revision=1)
    rejected = service.reject(
        message("m3", "confirm reject run-1", "run-1"), reason="missing behavior", report_revision=1
    )
    assert rejected.new_contract_revision == 2
    assert service.history("run-1")[0] == accepted
