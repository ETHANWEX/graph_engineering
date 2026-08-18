from __future__ import annotations

from pathlib import Path

import pytest

from graph_engineering.context import (
    ContextBuilder,
    ContextInput,
    Handoff,
    HandoffStatus,
    RepositoryMap,
)
from graph_engineering.executor import ExecutorRole, SessionPolicy
from graph_engineering.runtime.sessions import SessionRepository
from graph_engineering.runtime.store import StateStore


def test_handoff_is_structured_and_deterministic() -> None:
    handoff = Handoff(
        status=HandoffStatus.COMPLETED,
        summary="done",
        changed_files=["b.py", "a.py"],
        decisions=["keep API"],
        remaining_risks=[],
        next_actions=["verify"],
        evidence_refs=["artifact:2", "artifact:1"],
    )
    assert list(handoff.normalized().changed_files) == ["a.py", "b.py"]
    assert handoff.canonical_json() == handoff.normalized().canonical_json()


def test_context_builder_is_bounded_and_never_drops_contract() -> None:
    package = ContextBuilder(max_bytes=700).build(
        ContextInput(
            node_responsibility="Implement only node A",
            contract="IMMUTABLE CONTRACT: must remain present",
            global_policy="No network; preserve tests",
            git_status="clean",
            upstream_handoff="completed",
            failure_evidence="x" * 1000,
            file_refs=("z.py", "a.py"),
            artifact_refs=("artifact:z", "artifact:a"),
            output_schema="{status:string}",
        )
    )
    assert len(package.rendered.encode("utf-8")) <= 700
    assert "IMMUTABLE CONTRACT" in package.rendered
    assert package.file_refs == ("a.py", "z.py")


def test_required_context_larger_than_limit_fails() -> None:
    with pytest.raises(ValueError, match="immutable context"):
        ContextBuilder(max_bytes=50).build(
            ContextInput("node", "contract" * 20, "policy", "", "", "", (), (), "schema")
        )


def test_repository_map_rebuild_is_sorted_and_ignores_git_metadata(tmp_path: Path) -> None:
    (tmp_path / "b.py").write_text("b", encoding="utf-8")
    (tmp_path / "a.py").write_text("a", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    first = RepositoryMap.rebuild(tmp_path, use_git=False)
    second = RepositoryMap.rebuild(tmp_path, use_git=False)
    assert [entry.path for entry in first.entries] == ["a.py", "b.py"]
    assert first == second


def test_session_repository_persists_and_recovers_policy(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    assert state.latest_migration_version == 3
    sessions = SessionRepository(state)
    sessions.ensure_run_fixture("run-1")
    row = sessions.start(
        "run-1", "node", "attempt-1", ExecutorRole.IMPLEMENTER, "codex", "session-1", "0.147.0"
    )
    sessions.record_failure(row.session_id)
    recovered = SessionRepository(StateStore(tmp_path / "state.db")).latest("run-1", "node")
    assert recovered is not None
    assert recovered.provider_session_id == "session-1"
    assert SessionPolicy(max_continuations=1, rotate_after_failures=1).should_rotate(recovered)


def test_reviewer_session_policy_is_always_fresh() -> None:
    assert SessionPolicy().allows_resume(ExecutorRole.REVIEWER, same_node=True) is False
